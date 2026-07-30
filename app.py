import os
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
import urllib.parse

# --- 1. CONFIGURAÇÃO DA PÁGINA E FUSO HORÁRIO (BRASÍLIA) ---
st.set_page_config(page_title="Agendamento Online - Fio & Caixa", page_icon="✂️", layout="centered")

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

# Funções auxiliares para executar consultas garantindo permissão de escrita
def execute_write_query(query, params=None):
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE;"))
        if params:
            conn.execute(text(query), params)
        else:
            conn.execute(text(query))

def execute_read_query(query, params=None):
    with engine.connect() as conn:
        if params:
            result = conn.execute(text(query), params)
        else:
            result = conn.execute(text(query))
        return pd.DataFrame(result.fetchall(), columns=result.keys())

# --- 3. INICIALIZAÇÃO DAS TABELAS ---
def init_db():
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS agendamentos (
        id SERIAL PRIMARY KEY,
        estabelecimento VARCHAR(50) NOT NULL,
        cliente_nome VARCHAR(100) NOT NULL,
        cliente_telefone VARCHAR(20) NOT NULL,
        servico VARCHAR(100) NOT NULL,
        valor NUMERIC(10, 2) NOT NULL,
        data_hora TIMESTAMP WITH TIME ZONE NOT NULL,
        status VARCHAR(20) DEFAULT 'Agendado',
        criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS financeiro (
        id SERIAL PRIMARY KEY,
        estabelecimento VARCHAR(50) NOT NULL,
        descricao VARCHAR(200) NOT NULL,
        tipo VARCHAR(10) NOT NULL,
        valor NUMERIC(10, 2) NOT NULL,
        data DATE NOT NULL
    );
    """
    try:
        execute_write_query(create_tables_sql)
    except Exception as e:
        st.warning(f"Aviso na inicialização do banco: {e}")

init_db()

# --- 4. INTERFACE DO USUÁRIO ---
st.title("✂️ Fio & Caixa - Gestão e Agendamento")

# Configuração de Estabelecimento / Tenant
query_params = st.query_params
tenant_default = query_params.get("tenant", "Salao_Principal")

st.sidebar.header("🏢 Estabelecimento")
estabelecimento = st.sidebar.text_input("Nome/Slug do Salão:", value=tenant_default)

if not estabelecimento:
    st.info("Por favor, defina um identificador para o estabelecimento na barra lateral.")
    st.stop()

aba1, aba2, aba3 = st.tabs(["📅 Novo Agendamento", "📋 Meus Agendamentos", "💰 Financeiro"])

# ABA 1: NOVO AGENDAMENTO
with aba1:
    st.subheader("Agendar Cliente")
    with st.form("form_agendamento", clear_on_submit=True):
        nome = st.text_input("Nome do Cliente *")
        telefone = st.text_input("WhatsApp / Telefone *")
        
        col_serv, col_val = st.columns(2)
        with col_serv:
            servico = st.selectbox("Serviço", ["Corte Masculino", "Corte Feminino", "Barba", "Coloração", "Escova / Penteado", "Outro"])
        with col_val:
            valor = st.number_input("Valor (R$)", min_value=0.0, value=50.0, step=5.0)

        col_data, col_hora = st.columns(2)
        with col_data:
            data_agendamento = st.date_input("Data", min_value=datetime.now(TZ_BR).date())
        with col_hora:
            hora_agendamento = st.time_input("Horário", value=time(9, 0))

        submitted = st.form_submit_button("Confirmar Agendamento", use_container_width=True)

        if submitted:
            if not nome or not telefone:
                st.error("Preencha todos os campos obrigatórios (*).")
            else:
                data_hora_dt = datetime.combine(data_agendamento, hora_agendamento).replace(tzinfo=TZ_BR)
                
                insert_sql = """
                INSERT INTO agendamentos (estabelecimento, cliente_nome, cliente_telefone, servico, valor, data_hora)
                VALUES (:estabelecimento, :nome, :telefone, :servico, :valor, :data_hora);
                """
                try:
                    execute_write_query(insert_sql, {
                        "estabelecimento": estabelecimento,
                        "nome": nome,
                        "telefone": telefone,
                        "servico": servico,
                        "valor": valor,
                        "data_hora": data_hora_dt
                    })
                    st.success(f"✅ Agendamento de **{nome}** confirmado para {data_agendamento.strftime('%d/%m/%Y')} às {hora_agendamento.strftime('%H:%M')}!")
                except Exception as e:
                    st.error(f"❌ Erro ao salvar agendamento: {e}")

# ABA 2: VER AGENDAMENTOS
with aba2:
    st.subheader(f"Agendamentos - {estabelecimento}")
    
    col_filtro, _ = st.columns([1, 1])
    with col_filtro:
        data_filtro = st.date_input("Filtrar Data", value=datetime.now(TZ_BR).date())

    query_agenda = """
    SELECT id AS "ID", cliente_nome AS "Cliente", cliente_telefone AS "Telefone", 
           servico AS "Serviço", valor AS "Valor (R$)", 
           to_char(data_hora, 'HH24:MI') AS "Horário", status AS "Status"
    FROM agendamentos 
    WHERE estabelecimento = :estabelecimento AND DATE(data_hora AT TIME ZONE 'America/Sao_Paulo') = :data_filtro
    ORDER BY data_hora ASC;
    """
    
    try:
        df_agendamentos = execute_read_query(query_agenda, {
            "estabelecimento": estabelecimento,
            "data_filtro": data_filtro
        })
        
        if not df_agendamentos.empty:
            st.dataframe(df_agendamentos, use_container_width=True, hide_index=True)
            
            st.divider()
            with st.expander("Remover Agendamento"):
                id_cancelar = st.number_input("Digite o ID do agendamento para excluir", min_value=1, step=1)
                if st.button("Excluir Agendamento", type="secondary"):
                    delete_sql = "DELETE FROM agendamentos WHERE id = :id AND estabelecimento = :estabelecimento;"
                    execute_write_query(delete_sql, {"id": id_cancelar, "estabelecimento": estabelecimento})
                    st.success("Agendamento excluído!")
                    st.rerun()
        else:
            st.info("Nenhum agendamento encontrado para a data selecionada.")
    except Exception as e:
        st.error(f"Erro ao buscar agendamentos: {e}")

# ABA 3: FINANCEIRO
with aba3:
    st.subheader("Caixa & Lançamentos")
    
    with st.form("form_financeiro", clear_on_submit=True):
        col_desc, col_tipo, col_v = st.columns([2, 1, 1])
        with col_desc:
            desc = st.text_input("Descrição")
        with col_tipo:
            tipo = st.selectbox("Tipo", ["Receita", "Despesa"])
        with col_v:
            val_fin = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
        
        data_fin = st.date_input("Data do Lançamento", value=datetime.now(TZ_BR).date())
        sub_fin = st.form_submit_button("Lançar", use_container_width=True)

        if sub_fin:
            if not desc:
                st.error("Preencha a descrição do lançamento.")
            else:
                sql_fin = """
                INSERT INTO financeiro (estabelecimento, descricao, tipo, valor, data)
                VALUES (:estabelecimento, :desc, :tipo, :valor, :data);
                """
                try:
                    execute_write_query(sql_fin, {
                        "estabelecimento": estabelecimento,
                        "desc": desc,
                        "tipo": tipo,
                        "valor": val_fin,
                        "data": data_fin
                    })
                    st.success("Lançamento registrado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao registrar lançamento: {e}")

    st.divider()
    
    try:
        sql_resumo = """
        SELECT tipo, SUM(valor) as total 
        FROM financeiro 
        WHERE estabelecimento = :estabelecimento 
        GROUP BY tipo;
        """
        df_resumo = execute_read_query(sql_resumo, {"estabelecimento": estabelecimento})
        
        receitas = float(df_resumo[df_resumo['tipo'] == 'Receita']['total'].sum()) if not df_resumo.empty and 'Receita' in df_resumo['tipo'].values else 0.0
        despesas = float(df_resumo[df_resumo['tipo'] == 'Despesa']['total'].sum()) if not df_resumo.empty and 'Despesa' in df_resumo['tipo'].values else 0.0
        saldo = receitas - despesas

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Receitas", f"R$ {receitas:.2f}")
        col_m2.metric("Despesas", f"R$ {despesas:.2f}")
        col_m3.metric("Saldo Líquido", f"R$ {saldo:.2f}", delta=f"{saldo:.2f}")
        
    except Exception as e:
        st.error(f"Erro ao calcular balanço financeiro: {e}")
