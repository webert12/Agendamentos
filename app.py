import os
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
import urllib.parse

# --- 1. CONFIGURAÇÃO DA PÁGINA E FUSO HORÁRIO (BRASÍLIA) ---
st.set_page_config(page_title="Agendamento Online", page_icon="✂️", layout="centered")

# No Linux (Render), ZoneInfo precisa da biblioteca 'tzdata'
try:
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception as e:
    st.error("❌ Erro no fuso horário. Adicione 'tzdata' ao seu arquivo requirements.txt")
    st.stop()

# --- 2. CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
DB_URL = os.getenv("DB_URL")

if not DB_URL:
    try:
        DB_URL = st.secrets["DB_URL"]
    except Exception:
        st.error("❌ A variável DB_URL não foi configurada nas Environment Variables.")
        st.stop()

# CORREÇÃO CRÍTICA PARA O RENDER:
# O Render fornece URLs com 'postgres://', mas o SQLAlchemy exige 'postgresql://'
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

@st.cache_resource
def init_connection(url):
    return create_engine(url, pool_pre_ping=True)

# Inicializa o banco com tratamento de erro visível
try:
    engine = init_connection(DB_URL)
except Exception as e:
    st.error(f"❌ Erro ao conectar ao Banco de Dados: {e}")
    st.stop()
