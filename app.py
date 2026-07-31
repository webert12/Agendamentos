import os
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
import urllib.parse


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
# CONEXÃO COM BANCO SUPABASE
# =====================================================


def carregar_database_url():

    """
    Prioridade:

    1 - Variável de ambiente (Render)
    2 - Streamlit Secrets
    """

    db_url = None


    # Render / Ambiente
    if os.getenv("DB_URL"):

        db_url = os.getenv("DB_URL")


    # Streamlit Secrets
    elif "DB_URL" in st.secrets:

        db_url = st.secrets["DB_URL"]


    return db_url



DB_URL = carregar_database_url()



if not DB_URL:


    st.error(
        """
❌ DB_URL não encontrada.

Configure no Render:

Environment Variables

DB_URL=
sua_string_do_supabase
"""
    )

    st.stop()



# =====================================================
# CORREÇÕES DA STRING DE CONEXÃO
# =====================================================


# Render às vezes retorna postgres://

if DB_URL.startswith("postgres://"):

    DB_URL = DB_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )



# Corrige caracteres especiais na senha
# somente se necessário

try:

    url_temp = make_url(DB_URL)


    if url_temp.password:

        senha_original = url_temp.password


        senha_codificada = urllib.parse.quote_plus(
            senha_original
        )


        if senha_original != senha_codificada:

            DB_URL = DB_URL.replace(
                senha_original,
                senha_codificada
            )


except Exception:

    pass




# =====================================================
# DIAGNÓSTICO DA CONEXÃO
# =====================================================


try:

    url = make_url(DB_URL)


    with st.expander(
        "🔎 Diagnóstico da conexão"
    ):


        st.write(
            "Usuário:",
            url.username
        )


        st.write(
            "Host:",
            url.host
        )


        st.write(
            "Porta:",
            url.port
        )


        st.write(
            "Banco:",
            url.database
        )


        st.write(
            "Senha configurada:",
            "SIM" if url.password else "NÃO"
        )


except Exception as erro:


    st.warning(
        f"Não foi possível analisar a URL: {erro}"
    )




# =====================================================
# CRIAÇÃO DO ENGINE
# =====================================================


@st.cache_resource
def init_connection(url):


    return create_engine(

        url,


        # evita conexões quebradas

        pool_pre_ping=True,


        # recicla conexões antigas

        pool_recycle=180,


        # recomendado para Supabase Pooler

        pool_size=3,


        max_overflow=5,


        connect_args={

            "sslmode": "require",

            "connect_timeout": 10

        }

    )




try:


    engine = init_connection(DB_URL)



    # teste real da conexão

    with engine.connect() as conn:


        conn.execute(
            text("SELECT 1")
        )



except Exception as erro:


    st.error(
        f"""
❌ Falha ao conectar no banco.

Verifique:

1) Senha do banco Supabase
2) DB_URL no Render
3) Projeto Supabase correto
4) Região do Pooler

Erro técnico:

{erro}
"""
    )


    st.stop()
# =====================================================
# FUNÇÃO DE ESCRITA NO BANCO
# =====================================================


def execute_write(query, params=None):

    try:

        with engine.begin() as conn:

            conn.execute(
                text(query),
                params or {}
            )


        return True



    except SQLAlchemyError as erro:


        st.error(
            f"""
❌ Erro ao salvar no banco:

{erro}
"""
        )


        return False





# =====================================================
# FUNÇÃO DE LEITURA DO BANCO
# =====================================================


def execute_read(query, params=None):


    try:


        with engine.connect() as conn:


            resultado = conn.execute(

                text(query),

                params or {}

            )


            dados = resultado.fetchall()


            colunas = resultado.keys()



            return pd.DataFrame(

                dados,

                columns=colunas

            )



    except SQLAlchemyError as erro:


        st.error(

            f"""
❌ Erro ao consultar banco:

{erro}
"""

        )


        return pd.DataFrame()





# =====================================================
# TESTE DE SAÚDE DO BANCO
# =====================================================


def verificar_banco():


    try:


        resultado = execute_read(
            "SELECT NOW();"
        )


        if not resultado.empty:

            return True



    except Exception:

        pass



    return False





# =====================================================
# CRIAÇÃO DAS TABELAS
# =====================================================


def init_db():


    sql = """


    CREATE TABLE IF NOT EXISTS agendamentos (

        id SERIAL PRIMARY KEY,


        cliente_nome VARCHAR(100)
        NOT NULL,


        cliente_telefone VARCHAR(20)
        NOT NULL,


        servico VARCHAR(100)
        NOT NULL,


        data_hora TIMESTAMPTZ
        NOT NULL,


        criado_em TIMESTAMPTZ
        DEFAULT CURRENT_TIMESTAMP

    );


    """


    execute_write(sql)





# Inicializa banco

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


    st.subheader(
        "Marque seu Horário"
    )



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

                min_value=datetime.now(
                    TZ_BR
                ).date()

            )



        with col2:


            hora = st.time_input(

                "Horário",

                value=time(9,0)

            )




        enviar = st.form_submit_button(

            "Confirmar Agendamento",

            use_container_width=True

        )





        if enviar:



            nome = nome.strip()

            telefone = telefone.strip()



            if not nome:


                st.warning(
                    "Informe seu nome."
                )


                st.stop()



            if not telefone:


                st.warning(
                    "Informe seu telefone."
                )


                st.stop()





            # remove caracteres extras

            telefone_limpo = (

                telefone

                .replace(
                    "(",
                    ""
                )

                .replace(
                    ")",
                    ""
                )

                .replace(
                    "-",
                    ""
                )

                .replace(
                    " ",
                    ""
                )

            )





            data_hora = datetime.combine(

                data,

                hora

            ).replace(

                tzinfo=TZ_BR

            )





            # =====================================================
            # VERIFICA HORÁRIO EXISTENTE
            # =====================================================



            verifica_sql = """

            SELECT COUNT(*) AS total

            FROM agendamentos

            WHERE data_hora = :data_hora;

            """



            resultado = execute_read(

                verifica_sql,

                {

                    "data_hora": data_hora

                }

            )





            if not resultado.empty:



                quantidade = resultado.iloc[0]["total"]



                if quantidade > 0:



                    st.error(

                        "❌ Este horário já está reservado."

                    )


                    st.stop()







            # =====================================================
            # INSERÇÃO
            # =====================================================



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




            salvo = execute_write(


                insert_sql,


                {


                    "nome": nome,


                    "telefone": telefone_limpo,


                    "servico": servico,


                    "data_hora": data_hora


                }


            )






            if salvo:



                st.success(

                    f"""

✅ Agendamento confirmado!


👤 Cliente: {nome}


📅 Data:
{data.strftime('%d/%m/%Y')}


🕒 Horário:
{hora.strftime('%H:%M')}


✂️ Serviço:
{servico}

"""

                )



                st.rerun()
# =====================================================
# CONSULTA E CANCELAMENTO
# =====================================================


with aba_consultar:


    st.subheader(
        "📋 Consultar Agenda"
    )



    data_filtro = st.date_input(

        "Filtrar por Data",

        value=datetime.now(
            TZ_BR
        ).date(),

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


    WHERE DATE(

        data_hora AT TIME ZONE 'America/Sao_Paulo'

    ) = :data


    ORDER BY data_hora;


    """





    df = execute_read(

        query,

        {

            "data": data_filtro

        }

    )






    if not df.empty:



        # garante conversão correta

        df["data_hora"] = pd.to_datetime(

            df["data_hora"],

            utc=True

        ).dt.tz_convert(

            "America/Sao_Paulo"

        )



        df["Horário"] = df["data_hora"].dt.strftime(

            "%H:%M"

        )




        df = df.rename(

            columns={


                "id":

                "ID",



                "cliente_nome":

                "Cliente",



                "cliente_telefone":

                "Telefone",



                "servico":

                "Serviço"

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



        st.subheader(

            "❌ Cancelar Agendamento"

        )






        id_cancelar = st.number_input(

            "Digite o ID do agendamento",

            min_value=1,

            step=1

        )







        if st.button(

            "Cancelar Agendamento",

            use_container_width=True

        ):



            verificar = execute_read(

                """

                SELECT id

                FROM agendamentos

                WHERE id=:id;

                """,


                {

                    "id": id_cancelar

                }

            )





            if verificar.empty:



                st.warning(

                    "❌ Esse ID não existe."

                )



            else:



                apagou = execute_write(

                    """

                    DELETE FROM agendamentos

                    WHERE id=:id;

                    """,


                    {

                        "id": id_cancelar

                    }

                )





                if apagou:



                    st.success(

                        "✅ Agendamento cancelado."

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

    "✂️ Sistema de Agendamento • Versão Profissional"

)
