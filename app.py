import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
import urllib.parse
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA E CSS CUSTOMIZADO ---
st.set_page_config(page_title="Agendamento VIP", page_icon="✂️", layout="centered")

# Injeção de CSS para deixar o visual mais "Premium"
st.markdown("""
    <style>
    /* Ocultar elementos padrão do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Centralizar textos do cabeçalho */
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

    /* Estilizar o botão principal */
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
    
    /* Card de Sucesso Customizado */
    .success-card {
        background-color: #1e1e1e;
        padding: 25px;
        border-radius: 12px;
        border-left: 6px solid #00cc66;
        color: #ffffff;
        box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        margin-top: 20px;
    }
    .success-card h3 {
        margin-top: 0;
        color: #00cc66;
    }
    .success-card hr {
        border-color: #333333;
        margin: 15px 0;
    }
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

# --- CORREÇÃO AUTOMÁTICA DE ESTRUTURA DO BANCO ---
def ajustar_estrutura_banco():
    comandos_adicionar = [
        "ALTER TABLE agendamentos ADD COLUMN usuario_id VARCHAR(100) DEFAULT 'padrao';",
        "ALTER TABLE servicos ADD COLUMN usuario_id VARCHAR(100) DEFAULT 'padrao';",
        "ALTER TABLE agendamentos ADD COLUMN cliente_contato VARCHAR(100);",
        "ALTER TABLE agendamentos ADD COLUMN cliente_telefone VARCHAR(100);"
    ]
    for comando in comandos_adicionar:
        try:
            with engine.begin() as conn:
                conn.execute(text(comando))
        except Exception:
            pass 

    comandos_remover_restricao = [
        "ALTER TABLE agendamentos ALTER COLUMN cliente_telefone DROP NOT NULL;",
        "ALTER TABLE agendamentos ALTER COLUMN cliente_contato DROP NOT NULL;"
    ]
    for comando in comandos_remover_restricao:
        try:
            with engine.begin() as conn:
                conn.execute(text(comando))
        except Exception:
            pass 

ajustar_estrutura_banco()

# --- 3. HORÁRIOS PADRÃO DE ATENDIMENTO ---
HORARIOS_DISPONIVEIS = [
    "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "13:00", "13:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00"
]

# --- 4. FUNÇÕES DE BANCO DE DADOS ---
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
                return {row[0]: float(row[1]) for row in rows}
    except Exception:
        pass
    return {"Corte de Cabelo": 25.00, "Barba": 25.00, "Combo (Corte + Barba)": 50.00}

def buscar_horarios_ocupados(salao_id, data_str):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT hora FROM agendamentos WHERE usuario_id = :user AND data = :dt"),
                {"user": salao_clean, "dt": data_str}
            )
            ocupados = []
            for row in result.fetchall():
                val = str(row[0]).strip()
                if len(val) >= 5 and ":" in val:
                    ocupados.append(val[:5])
                else:
                    ocupados.append(val)
            return ocupados
    except Exception:
        return []

def salvar_agendamento(salao_id, cliente_nome, cliente_contato, servico_nome, data_str, hora):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    contato_clean = cliente_contato.strip()
    nome_clean = cliente_nome.strip()

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_contato, cliente_telefone, servico_nome, data, hora)
                VALUES (:user, :nome, :contato, :contato, :servico, :data, :hora)
                """),
                {"user": salao_clean, "nome": nome_clean, "contato": contato_clean, "servico": servico_nome, "data": data_str, "hora": hora}
            )
    except Exception:
        try:
            with engine.begin() as conn_fallback_1:
                conn_fallback_1.execute(
                    text("""
                    INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_telefone, servico_nome, data, hora)
                    VALUES (:user, :nome, :contato, :servico, :data, :hora)
                    """),
                    {"user": salao_clean, "nome": nome_clean, "contato": contato_clean, "servico": servico_nome, "data": data_str, "hora": hora}
                )
        except Exception:
            with engine.begin() as conn_fallback_2:
                conn_fallback_2.execute(
                    text("""
                    INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_contato, servico_nome, data, hora)
                    VALUES (:user, :nome, :contato, :servico, :data, :hora)
                    """),
                    {"user": salao_clean, "nome": nome_clean, "contato": contato_clean, "servico": servico_nome, "data": data_str, "hora": hora}
                )

# --- 5. PARÂMETROS DA URL E IDENTIFICAÇÃO DO SALÃO ---
query_params = st.query_params
salao_param = query_params.get("salao", "padrao")
salao_id_clean = urllib.parse.unquote(str(salao_param)).strip().lower()
nome_salao_formatado = salao_id_clean.replace('_', ' ').replace('-', ' ').title()

# --- 6. INTERFACE DE AGENDAMENTO (VISUAL MODERNO) ---

# Cabeçalho customizado via HTML
st.markdown(f"<h1 class='title-text'>✂️ {nome_salao_formatado}</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle-text'>Agendamento Online Rápido e Profissional</p>", unsafe_allow_html=True)

servicos_disponiveis = carregar_servicos_salao(salao_id_clean)
agora_br = datetime.now(TZ_BR)
hoje_str = agora_br.strftime("%Y-%m-%d")
hora_atual_str = agora_br.strftime("%H:%M")

# Divisória estilosa
st.markdown("---")

# SELEÇÃO DE DATA
data_escolhida = st.date_input("📅 Escolha o Dia do Agendamento:", min_value=agora_br.date())
data_str = data_escolhida.strftime("%Y-%m-%d")
ocupados = buscar_horarios_ocupados(salao_id_clean, data_str)

opcoes_horario = ["-- Selecione o Horário --"]
for h in HORARIOS_DISPONIVEIS:
    eh_passado = (data_str == hoje_str) and (h <= hora_atual_str)
    eh_reservado = h in ocupados

    if eh_passado:
        opcoes_horario.append(f"🔴 {h} - (HORÁRIO JÁ PASSOU)")
    elif eh_reservado:
        opcoes_horario.append(f"🔴 {h} - (RESERVADO)")
    else:
        opcoes_horario.append(f"🟢 {h} - (DISPONÍVEL)")

# FORMULÁRIO DE DADOS DO CLIENTE
with st.form("form_agendamento_cliente", clear_on_submit=False):
    
    # Organizando campos lado a lado para telas maiores
    col1, col2 = st.columns(2)
    with col1:
        nome_cliente = st.text_input("👤 Seu Nome Completo:")
    with col2:
        telefone_cliente = st.text_input("📱 Seu WhatsApp (com DDD):")

    if servicos_disponiveis:
        servico_escolhido = st.selectbox(
            "✂️ Escolha o Serviço Desejado:",
            options=list(servicos_disponiveis.keys()),
            format_func=lambda x: f"{x} - R$ {servicos_disponiveis[x]:.2f}"
        )
    else:
        st.warning("Nenhum serviço disponível no momento.")
        servico_escolhido = None
        
    horario_selecionado = st.selectbox("⏰ Escolha o Horário Desejado:", options=opcoes_horario)
    
    # Botão de envio
    st.write("") # Espaçamento
    enviar = st.form_submit_button("Confirmar Agendamento 🚀", use_container_width=True)

# --- 7. PROCESSAMENTO E MENSAGEM DE CONFIRMAÇÃO ---
if enviar:
    if not nome_cliente or not telefone_cliente:
        st.warning("⚠️ Por favor, preencha seu nome e WhatsApp.")
    elif not servico_escolhido:
        st.error("⚠️ Selecione um serviço válido.")
    elif horario_selecionado == "-- Selecione o Horário --":
        st.warning("⚠️ Por favor, escolha um horário na lista acima.")
    elif "🔴" in horario_selecionado:
        hora_ext = horario_selecionado.split()[1]
        if "HORÁRIO JÁ PASSOU" in horario_selecionado:
            st.error(f"❌ O horário {hora_ext} já passou. Escolha um horário futuro.")
        else:
            st.error(f"❌ O horário {hora_ext} já possui uma reserva. Escolha um horário verde (🟢).")
    else:
        hora_limpa = horario_selecionado.split()[1]
        ocupados_agora = buscar_horarios_ocupados(salao_id_clean, data_str)
        
        if hora_limpa in ocupados_agora:
            st.error(f"❌ O horário **{hora_limpa}** acabou de ser reservado. Escolha outro horário.")
        else:
            try:
                salvar_agendamento(
                    salao_id=salao_id_clean, cliente_nome=nome_cliente, 
                    cliente_contato=telefone_cliente, servico_nome=servico_escolhido, 
                    data_str=data_str, hora=hora_limpa
                )
                st.balloons()
                
                # MENSAGEM DE SUCESSO PROFISSIONAL (Card HTML)
                mensagem_sucesso = f"""
                <div class="success-card">
                    <h3>🎉 Agendamento Confirmado!</h3>
                    <p>Olá, <b>{nome_cliente}</b>! Seu horário foi reservado com sucesso no sistema.</p>
                    <hr>
                    <p>📅 <b>Data:</b> {data_escolhida.strftime('%d/%m/%Y')}</p>
                    <p>⏰ <b>Horário:</b> {hora_limpa}</p>
                    <p>✂️ <b>Serviço:</b> {servico_escolhido}</p>
                    <br>
                    <p style="font-size: 13px; color: #bbbbbb;">
                        Agradecemos a preferência! Por favor, chegue com 5 minutos de antecedência.
                    </p>
                </div>
                """
                st.markdown(mensagem_sucesso, unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Ocorreu um erro ao salvar o agendamento: {e}")
