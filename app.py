import os
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

# =====================================================
# CONFIGURAÇÃO DA PÁGINA
# =====================================================

st.set_page_config(
    page_title="Agendamento Online",
    page_icon="✂️",
    layout="centered"
)

# =====================================================
# FUSO HORÁRIO
# =====================================================

try:
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    st.error(
        "❌ Erro ao carregar o fuso horário.\n\n"
        "Adicione 'tzdata' ao requirements.txt"
    )
    st.stop()

# =====================================================
# CONEXÃO COM O BANCO
# =====================================================

DB_URL = os.getenv("DB_URL")

if not DB_URL:
    try:
        DB_URL = st.secrets["DB_URL"]
    except Exception:
        st.error(
            "❌ A variável DB_URL não foi encontrada."
        )
        st.stop()

# Corrige postgres://
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

# =====================================================
# DIAGNÓSTICO
# =====================================================

try:

    url = make_url(DB_URL)

    with st.expander("Diagnóstico da conexão"):

        st.write("Usuário:", url.username)

        st.write("Host:", url.host)

        st.write("Porta:", url.port)

        st.write("Banco:", url.database)

except Exception:
    pass

# =====================================================
# ENGINE
# =====================================================

@st.cache_resource
def init_connection(url):

    return create_engine(

        url,

        pool_pre_ping=True,

        pool_recycle=300,

        pool_size=5,

        max_overflow=10,

        connect_args={

            "sslmode": "require",

            "connect_timeout": 20

        }

    )

try:

    engine = init_connection(DB_URL)

except Exception as e:

    st.error(f"❌ Erro ao conectar:\n\n{e}")

    st.stop()

# =====================================================
# ESCRITA
# =====================================================

def execute_write(query, params=None):

    try:

        with engine.begin() as conn:

            conn.execute(text(query), params or {})

        return True

    except SQLAlchemyError as e:

        st.error(f"Erro no banco:\n\n{e}")

        return False

# =====================================================
# LEITURA
# =====================================================

def execute_read(query, params=None):

    try:

        with engine.begin() as conn:

            result = conn.execute(

                text(query),

                params or {}

            )

            return pd.DataFrame(

                result.fetchall(),

                columns=result.keys()

            )

    except SQLAlchemyError as e:

        st.error(f"Erro ao consultar:\n\n{e}")

        return pd.DataFrame()

# =====================================================
# CRIAÇÃO DAS TABELAS
# =====================================================

def init_db():

    sql = """

    CREATE TABLE IF NOT EXISTS agendamentos (

        id SERIAL PRIMARY KEY,

        cliente_nome VARCHAR(100) NOT NULL,

        cliente_telefone VARCHAR(20) NOT NULL,

        servico VARCHAR(100) NOT NULL,

        data_hora TIMESTAMPTZ NOT NULL,

        criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

    );

    """

    execute_write(sql)

init_db()
# =====================================================
# INTERFACE
# =====================================================

st.title("✂️ Agendamento Online")

aba_novo, aba_consultar = st.tabs(
    [
        "📅 Novo Agendamento",
        "📋 Horários Agendados"
    ]
)

# =====================================================
# NOVO AGENDAMENTO
# =====================================================

with aba_novo:

    st.subheader("Marque seu Horário")

    with st.form(
        "form_agendamento",
        clear_on_submit=True
    ):

        nome = st.text_input(
            "Nome Completo *"
        )

        telefone = st.text_input(
            "WhatsApp / Telefone *"
        )

        servico = st.selectbox(

            "Serviço",

            [

                "Corte Masculino",

                "Corte Feminino",

                "Barba",

                "Sobrancelha",

                "Outro"

            ]

        )

        col1, col2 = st.columns(2)

        with col1:

            data = st.date_input(

                "Data",

                min_value=datetime.now(TZ_BR).date()

            )

        with col2:

            hora = st.time_input(

                "Horário",

                value=time(9, 0)

            )

        enviar = st.form_submit_button(

            "Confirmar Agendamento",

            use_container_width=True

        )

        if enviar:

            if not nome.strip():

                st.warning("Informe seu nome.")

            elif not telefone.strip():

                st.warning("Informe seu telefone.")

            else:

                data_hora = datetime.combine(
                    data,
                    hora
                ).replace(
                    tzinfo=TZ_BR
                )

                verifica_sql = """

                SELECT COUNT(*)

                FROM agendamentos

                WHERE data_hora=:data_hora;

                """

                qtd = execute_read(

                    verifica_sql,

                    {

                        "data_hora": data_hora

                    }

                )

                if not qtd.empty:

                    if qtd.iloc[0,0] > 0:

                        st.error(

                            "❌ Já existe um horário marcado para esse horário."

                        )

                        st.stop()

                insert_sql = """

                INSERT INTO agendamentos

                (

                    cliente_nome,

                    cliente_telefone,

                    servico,

                    data_hora

                )

                VALUES

                (

                    :nome,

                    :telefone,

                    :servico,

                    :data_hora

                );

                """

                ok = execute_write(

                    insert_sql,

                    {

                        "nome": nome,

                        "telefone": telefone,

                        "servico": servico,

                        "data_hora": data_hora

                    }

                )

                if ok:

                    st.success(

                        f"""

✅ Agendamento confirmado!

👤 {nome}

📅 {data.strftime('%d/%m/%Y')}

🕒 {hora.strftime('%H:%M')}

✂️ {servico}

"""

                    )

                    st.rerun()
                    # =====================================================
# CONSULTA E CANCELAMENTO
# =====================================================

with aba_consultar:

    st.subheader("Consultar Agenda")

    data_filtro = st.date_input(
        "Filtrar por Data",
        value=datetime.now(TZ_BR).date(),
        key="data_filtro"
    )

    query = """
    SELECT
        id,
        cliente_nome,
        cliente_telefone,
        servico,
        data_hora
    FROM agendamentos
    WHERE DATE(data_hora AT TIME ZONE 'America/Sao_Paulo') = :data
    ORDER BY data_hora;
    """

    df = execute_read(
        query,
        {
            "data": data_filtro
        }
    )

    if not df.empty:

        df["Horário"] = pd.to_datetime(
            df["data_hora"]
        ).dt.strftime("%H:%M")

        df = df.rename(
            columns={
                "id": "ID",
                "cliente_nome": "Cliente",
                "cliente_telefone": "Telefone",
                "servico": "Serviço"
            }
        )

        st.dataframe(
            df[
                [
                    "ID",
                    "Cliente",
                    "Telefone",
                    "Serviço",
                    "Horário"
                ]
            ],
            hide_index=True,
            use_container_width=True
        )

        st.divider()

        st.subheader("Cancelar Agendamento")

        id_cancelar = st.number_input(
            "Informe o ID",
            min_value=1,
            step=1
        )

        if st.button(
            "❌ Cancelar Agendamento",
            use_container_width=True
        ):

            existe = execute_read(
                """
                SELECT id
                FROM agendamentos
                WHERE id=:id;
                """,
                {
                    "id": id_cancelar
                }
            )

            if existe.empty:

                st.warning(
                    "ID não encontrado."
                )

            else:

                ok = execute_write(
                    """
                    DELETE FROM agendamentos
                    WHERE id=:id;
                    """,
                    {
                        "id": id_cancelar
                    }
                )

                if ok:

                    st.success(
                        "Agendamento cancelado com sucesso."
                    )

                    st.rerun()

    else:

        st.info(
            "Nenhum agendamento encontrado para esta data."
        )

# =====================================================
# RODAPÉ
# =====================================================

st.divider()

st.caption(
    "Sistema de Agendamento • Versão Profissional"
            )
