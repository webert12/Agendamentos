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
