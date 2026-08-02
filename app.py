import streamlit as st
import os
import urllib.parse
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text

# --- 1. CONFIGURAÇÃO DA PÁGINA E CSS CUSTOMIZADO ---
st.set_page_config(page_title="Agendamento VIP", page_icon="✂️", layout="centered")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .title-text {
        text-align: center;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
        margin-bottom: 0px;
    }
    .subtitle-text {
        text-align: center;
        color: #888888;
        font-size: 16px;
        margin-bottom: 30px;
    }

    div.stButton > button:first-child {
        background: linear-gradient(90deg, #d31027 0%, #ea384d 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        font-size: 18px;
        font-weight: bold;
        transition: all 0.3s ease;
        box-shadow: 0px 4px 15px rgba(234, 56, 77, 0.4);
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0px 6px 20px rgba(234, 56, 77, 0.6);
    }
    
    .success-card {
        background-color: #1e1e1e;
        padding: 25px;
        border-radius: 12px;
        border-left: 6px solid #00cc66;
        color: #ffffff;
        box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        margin-top: 20px;
        margin-bottom: 20px;
    }
    .success-card h3 { margin-top: 0; color: #00cc66; }
    .success-card hr { border-color: #333333; margin: 15px 0; }
    
    /* Estilo para o botão do WhatsApp */
    .btn-whatsapp {
        display: block;
        text-align: center;
        background-color: #25D366;
        color: white !important;
        text-decoration: none;
        padding: 12px;
        border-radius: 8px;
        font-weight: bold;
        margin-top: 10px;
    }
    .btn-whatsapp:hover { background-color: #128C7E; }
    </style>
""", unsafe_allow_html=True)

TZ_BR = ZoneInfo("America/Sao_Paulo")

# --- 2. CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
DB_URL = os.environ.get("DB_URL")

if not DB_URL:
    try:
        if "DB_URL" in st.secrets:
            DB_URL = st.secrets["DB_URL"]
    except FileNotFoundError:
        pass 

if not DB_URL:
    st.error("❌ ERRO: A variável 'DB_URL' não foi encontrada.")
    st.stop()

@st.cache_resource
def init_connection(url):
    return create_engine(url, pool_pre_ping=True)

try:
    engine = init_connection(DB_URL)
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")
    st.stop()

# --- 3. HORÁRIOS DISPONÍVEIS ---
HORARIOS_DISPONIVEIS = [
    "08:00", "09:00", "10:00", "11:00", 
    "13:00", "14:00", "15:00", "16:00", 
    "17:00", "18:00", "19:00"
]

# --- 4. FUNÇÕES DE BANCO DE DADOS (ORIGINAIS E LIMPAS) ---
def carregar_servicos_salao(salao_id):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT nome, preco FROM servicos WHERE usuario_id = :user ORDER BY nome ASC"),
                {"user": salao_clean}
            )
            rows = result.fetchall()
            if rows:
                return {row[0]: {"preco": float(row[1]), "duracao": 30} for row in rows}
    except Exception:
        pass
        
    # Fallback padrão caso o banco esteja vazio
    return {
        "Corte de Cabelo": {"preco": 25.00, "duracao": 30},
        "Barba": {"preco": 25.00, "duracao": 30},
        "Combo (Corte + Barba)": {"preco": 50.00, "duracao": 30}
    }

def buscar_horarios_ocupados(salao_id, data_str):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    horarios_bloqueados = []
    try:
        with engine.connect() as conn:
            query = text("SELECT hora FROM agendamentos WHERE usuario_id = :user AND data = :dt")
            result = conn.execute(query, {"user": salao_clean, "dt": data_str})
            
            for row in result.fetchall():
                hora_agendada = str(row[0]).strip()[:5]
                horarios_bloqueados.append(hora_agendada)
                    
            return set(horarios_bloqueados)
    except Exception:
        return set()

def salvar_agendamento(salao_id, cliente_nome, cliente_telefone, servico_nome, data_str, hora):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    
    # Remove formatações do telefone para salvar limpo no banco
    telefone_clean = re.sub(r'\D', '', cliente_telefone)

    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_contato, servico_nome, data, hora)
            VALUES (:user, :nome, :telefone, :servico, :data, :hora)
            """),
            {"user": salao_clean, "nome": cliente_nome.strip(), "telefone": telefone_clean, 
             "servico": servico_nome, "data": data_str, "hora": hora}
        )

# --- 5. PARÂMETROS DA URL E IDENTIFICAÇÃO DO SALÃO ---
query_params = st.query_params
salao_param = query_params.get("salao", "padrao")
salao_id_clean = urllib.parse.unquote(str(salao_param)).strip().lower()
nome_salao_formatado = salao_id_clean.replace('_', ' ').replace('-', ' ').title()

# --- 6. INTERFACE DE AGENDAMENTO ---
st.markdown(f"<h1 class='title-text'>✂️ {nome_salao_formatado}</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle-text'>Agendamento Online Rápido e Profissional</p>", unsafe_allow_html=True)
st.markdown("---")

agora_br = datetime.now(TZ_BR)
hoje_str = agora_br.strftime("%Y-%m-%d")
hora_atual_str = agora_br.strftime("%H:%M")

servicos_disponiveis = carregar_servicos_salao(salao_id_clean)

# ETAPA 1: ESCOLHER DATA E SERVIÇO (Fora do formulário principal)
col_data, col_servico = st.columns(2)
with col_data:
    data_escolhida = st.date_input("📅 Escolha o Dia:", min_value=agora_br.date())
    data_str = data_escolhida.strftime("%Y-%m-%d")

with col_servico:
    if servicos_disponiveis:
        servico_escolhido = st.selectbox(
            "✂️ Escolha o Serviço:",
            options=list(servicos_disponiveis.keys()),
            format_func=lambda x: f"{x} - R$ {servicos_disponiveis[x]['preco']:.2f}"
        )
    else:
        st.warning("Nenhum serviço disponível no momento.")
        servico_escolhido = None

# ETAPA 2: FILTRAR HORÁRIOS VÁLIDOS
ocupados = buscar_horarios_ocupados(salao_id_clean, data_str)
opcoes_horario = ["-- Selecione o Horário --"]

for h in HORARIOS_DISPONIVEIS:
    # Pula horários que já passaram hoje
    if data_str == hoje_str and h <= hora_atual_str:
        continue
        
    # Adiciona apenas se o horário estiver livre
    if h not in ocupados:
        opcoes_horario.append(h)

# ETAPA 3: FORMULÁRIO DE CLIENTE
with st.form("form_agendamento_cliente", clear_on_submit=False):
    st.markdown("### Preencha seus dados para confirmar")
    
    col1, col2 = st.columns(2)
    with col1:
        nome_cliente = st.text_input("👤 Seu Nome Completo:")
    with col2:
        telefone_cliente = st.text_input("📱 WhatsApp (com DDD):", placeholder="Ex: 11999999999")
        
    if len(opcoes_horario) == 1:
        st.warning("⚠️ Não há horários disponíveis nesta data.")
        horario_selecionado = "-- Selecione o Horário --"
    else:
        horario_selecionado = st.selectbox("⏰ Horário Disponível:", options=opcoes_horario)
    
    st.write("")
    enviar = st.form_submit_button("Confirmar Agendamento 🚀", use_container_width=True)

# --- 7. PROCESSAMENTO DO ENVIO ---
if enviar:
    if not nome_cliente or not telefone_cliente:
        st.error("⚠️ Por favor, preencha seu nome e WhatsApp.")
    elif not servico_escolhido:
        st.error("⚠️ Selecione um serviço válido.")
    elif horario_selecionado == "-- Selecione o Horário --":
        st.error("⚠️ Por favor, escolha um horário na lista.")
    else:
        try:
            salvar_agendamento(
                salao_id=salao_id_clean, 
                cliente_nome=nome_cliente, 
                cliente_telefone=telefone_cliente, 
                servico_nome=servico_escolhido, 
                data_str=data_str, 
                hora=horario_selecionado
            )
            st.balloons()
            
            # Gera link do WhatsApp (O cliente clica e envia mensagem para o salão)
            texto_wa = urllib.parse.quote(f"Olá! Acabei de agendar um(a) {servico_escolhido} para o dia {data_escolhida.strftime('%d/%m/%Y')} às {horario_selecionado}. Meu nome é {nome_cliente}.")
            link_wa = f"https://wa.me/?text={texto_wa}"
            
            mensagem_sucesso = f"""
            <div class="success-card">
                <h3>🎉 Agendamento Confirmado!</h3>
                <p>Olá, <b>{nome_cliente}</b>! Seu horário foi reservado com sucesso.</p>
                <hr>
                <p>📅 <b>Data:</b> {data_escolhida.strftime('%d/%m/%Y')}</p>
                <p>⏰ <b>Horário:</b> {horario_selecionado}</p>
                <p>✂️ <b>Serviço:</b> {servico_escolhido}</p>
                <br>
                <a href="{link_wa}" target="_blank" class="btn-whatsapp">
                    📱 Enviar Confirmação no WhatsApp
                </a>
            </div>
            """
            st.markdown(mensagem_sucesso, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"❌ Ocorreu um erro ao salvar o agendamento no banco de dados. Detalhes: {e}")
