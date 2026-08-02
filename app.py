import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
import urllib.parse

# --- 1. CONFIGURAÇÃO DA PÁGINA E FUSO HORÁRIO (BRASÍLIA) ---
st.set_page_config(page_title="Agendamento Online", page_icon="✂️", layout="centered")
TZ_BR = ZoneInfo("America/Sao_Paulo")

# --- 2. CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
if "DB_URL" in st.secrets:
    DB_URL = st.secrets["DB_URL"]
else:
    st.error("❌ ERRO: A variável 'DB_URL' não foi encontrada nos Secrets do Streamlit Cloud.")
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
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE agendamentos ALTER COLUMN cliente_telefone DROP NOT NULL;"))
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

    with engine.begin() as conn:
        try:
            conn.execute(
                text("""
                    INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_contato, cliente_telefone, servico_nome, data, hora)
                    VALUES (:user, :nome, :contato, :contato, :servico, :data, :hora)
                """),
                {
                    "user": salao_clean,
                    "nome": nome_clean,
                    "contato": contato_clean,
                    "servico": servico_nome,
                    "data": data_str,
                    "hora": hora
                }
            )
        except Exception:
            conn.execute(
                text("""
                    INSERT INTO agendamentos (usuario_id, cliente_nome, cliente_contato, servico_nome, data, hora)
                    VALUES (:user, :nome, :contato, :servico, :data, :hora)
                """),
                {
                    "user": salao_clean,
                    "nome": nome_clean,
                    "contato": contato_clean,
                    "servico": servico_nome,
                    "data": data_str,
                    "hora": hora
                }
            )

# --- 5. PARÂMETROS DA URL E IDENTIFICAÇÃO DO SALÃO ---
query_params = st.query_params
salao_param = query_params.get("salao", "padrao")
salao_id_clean = urllib.parse.unquote(str(salao_param)).strip().lower()
nome_salao_formatado = salao_id_clean.replace('_', ' ').replace('-', ' ').title()

# --- 6. INTERFACE DE AGENDAMENTO DO CLIENTE ---
st.title("✂️ Agendamento Online")
st.write(f"Seja bem-vindo ao sistema de agendamento de **{nome_salao_formatado}**.")

servicos_disponiveis = carregar_servicos_salao(salao_id_clean)

# Obter data e hora atual no fuso de Brasília
agora_br = datetime.now(TZ_BR)
hoje_str = agora_br.strftime("%Y-%m-%d")
hora_atual_str = agora_br.strftime("%H:%M")

# --- SELEÇÃO DE DATA FORA DO FORMULÁRIO PARA ATUALIZAÇÃO INSTANTÂNEA ---
data_escolhida = st.date_input("Escolha o Dia do Agendamento:", min_value=agora_br.date())
data_str = data_escolhida.strftime("%Y-%m-%d")

# Consulta no banco de dados para a data recém-selecionada
ocupados = buscar_horarios_ocupados(salao_id_clean, data_str)

# Monta a lista dinâmica de opções imediatamente
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

# --- FORMULÁRIO DE DADOS DO CLIENTE ---
with st.form("form_agendamento_cliente", clear_on_submit=True):
    nome_cliente = st.text_input("Seu Nome Completo:")
    telefone_cliente = st.text_input("Seu WhatsApp (com DDD):")
    
    if servicos_disponiveis:
        servico_escolhido = st.selectbox(
            "Escolha o Serviço Desejado:", 
            options=list(servicos_disponiveis.keys()),
            format_func=lambda x: f"{x} - R$ {servicos_disponiveis[x]:.2f}"
        )
    else:
        st.warning("Nenhum serviço disponível no momento.")
        servico_escolhido = None

    horario_selecionado = st.selectbox(
        "Escolha o Horário Desejado:", 
        options=opcoes_horario
    )

    enviar = st.form_submit_button("Confirmar Agendamento 🚀", use_container_width=True)

# --- 7. PROCESSAMENTO E VALIDAÇÃO DO FORMULÁRIO ---
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
            st.error(f"❌ O horário **{hora_ext}** já passou para a data selecionada. Escolha um horário futuro.")
        else:
            st.error(f"❌ O horário **{hora_ext}** já possui uma reserva confirmada para esta data. Escolha um horário verde (🟢).")
    else:
        hora_limpa = horario_selecionado.split()[1]
        
        # Checagem em tempo real antes de salvar
        ocupados_agora = buscar_horarios_ocupados(salao_id_clean, data_str)
        if hora_limpa in ocupados_agora:
            st.error(f"❌ O horário **{hora_limpa}** acabou de ser reservado nesta data por outro cliente. Escolha outro horário.")
        else:
            try:
                salvar_agendamento(
                    salao_id=salao_id_clean,
                    cliente_nome=nome_cliente,
                    cliente_contato=telefone_cliente,
                    servico_nome=servico_escolhido,
                    data_str=data_str,
                    hora=hora_limpa
                )
                
                st.success(f"🎉 Agendamento confirmado com sucesso, {nome_cliente}!")
                st.balloons()
                st.info(
                    f"📅 **Data:** {data_escolhida.strftime('%d/%m/%Y')} às **{hora_limpa}**\n\n"
                    f"✂️ **Serviço:** {servico_escolhido}"
                )
            except Exception as e:
                st.error(f"Ocorreu um erro ao salvar o agendamento: {e}")
