import os
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text

# --- 1. CONFIGURAÇÃO DA PÁGINA E FUSO HORÁRIO (BRASÍLIA) ---
st.set_page_config(page_title="Agendamento Online", page_icon="✂️", layout="centered")

try:
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    st.error("❌ Erro no fuso horário. Adicione 'tzdata' ao seu arquivo requirements.txt")
    st.stop()

# --- 2. CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
DB_URL = os.getenv("DB_URL")

if not DB_URL:
    try:
        DB_URL = st.secrets["DB_URL"]
    except Exception:
        st.error("❌ ERRO: A variável 'DB_URL' não foi encontrada nas Environment Variables nem nos Secrets.")
        st.stop()

# Correção para o Render (SQLAlchemy exige postgresql://)
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

@st.cache_resource
def init_connection(url):
    return create_engine(url, pool_pre_ping=True)

try:
    engine = init_connection(DB_URL)
except Exception as e:
    st.error(f"❌ Erro ao conectar ao Banco de Dados: {e}")
    st.stop()

# Executores de consulta com liberação de escrita no PostgreSQL do Render
def execute_write(query, params=None):
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE;"))
        if params:
            conn.execute(text(query), params)
        else:
            conn.execute(text(query))

def execute_read(query, params=None):
    with engine.connect() as conn:
        if params:
            result = conn.execute(text(query), params)
        else:
            result = conn.execute(text(query))
        return pd.DataFrame(result.fetchall(), columns=result.keys())

# --- 3. CRIAR TABELA SE NÃO EXISTIR ---
def init_db():
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS agendamentos (
        id SERIAL PRIMARY KEY,
        cliente_nome VARCHAR(100) NOT NULL,
        cliente_telefone VARCHAR(20) NOT NULL,
        servico VARCHAR(100) NOT NULL,
        data_hora TIMESTAMP WITH TIME ZONE NOT NULL,
        criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        execute_write(create_table_sql)
    except Exception as e:
        st.warning(f"Aviso na verificação do banco: {e}")

init_db()

# --- 4. INTERFACE DO SISTEMA DE AGENDAMENTO ---
st.title("✂️ Agendamento Online")

aba_novo, aba_consultar = st.tabs(["📅 Novo Agendamento", "📋 Horários Agendados"])

# ABA DE CADASTRO DE AGENDAMENTO
with aba_novo:
    st.subheader("Marque seu Horário")
    
    with st.form("form_agendamento", clear_on_submit=True):
        nome = st.text_input("Nome Completo *")
        telefone = st.text_input("WhatsApp / Telefone *")
        servico = st.selectbox("Serviço Desejado", ["Corte Masculino", "Corte Feminino", "Barba", "Sobrancelha", "Outro"])
        
        col_data, col_hora = st.columns(2)
        with col_data:
            data = st.date_input("Data", min_value=datetime.now(TZ_BR).date())
        with col_hora:
            hora = st.time_input("Horário", value=time(9, 0))

        btn_agendar = st.form_submit_button("Confirmar Agendamento", use_container_width=True)

        if btn_agendar:
            if not nome.strip() or not telefone.strip():
                st.error("Por favor, preencha o Nome e o Telefone.")
            else:
                dt_completa = datetime.combine(data, hora).replace(tzinfo=TZ_BR)
                insert_sql = """
                INSERT INTO agendamentos (cliente_nome, cliente_telefone, servico, data_hora)
                VALUES (:nome, :telefone, :servico, :data_hora);
                """
                try:
                    execute_write(insert_sql, {
                        "nome": nome,
                        "telefone": telefone,
                        "servico": servico,
                        "data_hora": dt_completa
                    })
                    st.success(f"✅ Agendamento de **{nome}** confirmado para {data.strftime('%d/%m/%Y')} às {hora.strftime('%H:%M')}!")
                except Exception as e:
                    st.error(f"❌ Erro ao salvar agendamento: {e}")

# ABA DE CONSULTA E CANCELAMENTO
with aba_consultar:
    st.subheader("Consultar Agenda")
    
    data_filtro = st.date_input("Filtrar por Data", value=datetime.now(TZ_BR).date())
    
    query_busca = """
    SELECT 
        id AS "ID", 
        cliente_nome AS "Cliente", 
        cliente_telefone AS "Telefone", 
        servico AS "Serviço", 
        to_char(data_hora AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI') AS "Horário"
    FROM agendamentos
    WHERE DATE(data_hora AT TIME ZONE 'America/Sao_Paulo') = :data_filtro
    ORDER BY data_hora ASC;
    """
    
    try:
        df = execute_read(query_busca, {"data_filtro": data_filtro})
        
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.divider()
            col_id, col_btn = st.columns([2, 1])
            with col_id:
                id_deletar = st.number_input("ID do agendamento para cancelar", min_value=1, step=1)
            with col_btn:
                st.write("")
                st.write("")
                if st.button("Cancelar Horário", type="secondary"):
                    execute_write("DELETE FROM agendamentos WHERE id = :id;", {"id": id_deletar})
                    st.success("Agendamento cancelado com sucesso!")
                    st.rerun()
        else:
            st.info("Nenhum agendamento encontrado para a data selecionada.")
    except Exception as e:
        st.error(f"Erro ao buscar agendamentos: {e}")
