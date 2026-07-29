import os
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
DB_URL = os.getenv("DB_URL")

if not DB_URL:
    try:
        DB_URL = st.secrets["DB_URL"]
    except Exception:
        st.error("❌ A variável DB_URL não foi configurada.")
        st.stop()

@st.cache_resource
def init_connection(url):
    return create_engine(url, pool_pre_ping=True)
