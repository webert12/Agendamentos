import os
import re
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# --- 1. CONFIGURAÇÃO DA PÁGINA E FUSO HORÁRIO (BRASÍLIA) ---
st.set_page_config(page_title="Agendamento Online", page_icon="✂️", layout="centered")
TZ_BR = ZoneInfo("America/Sao_Paulo")

# --- 2. CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
DB_URL = os.getenv("DB_URL")

if not DB_URL:
    try:
        if "DB_URL" in st.secrets:
            DB_URL = st.secrets["DB_URL"]
    except Exception:
        pass

if not DB_URL:
    st.error("❌ ERRO: A variável 'DB_URL' não foi encontrada nas Variáveis de Ambiente nem nos Secrets do Streamlit.")
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
def buscar_dados_salao(salao_id):
    """Busca os serviços e o WhatsApp do salão cadastrado no Supabase."""
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    servicos = {}
    whatsapp = ""
    
    try:
        with engine.connect() as conn:
            # 1. Busca o WhatsApp do salão na tabela de usuários
            res_user = conn.execute(
                text("SELECT whatsapp FROM usuarios WHERE usuario_id = :user"), 
                {"user": salao_clean}
            ).fetchone()
            if res_user and res_user[0]:
                whatsapp = str(res_user[0])

            # 2. Busca os serviços cadastrados do salão
            res_serv = conn.execute(
                text("SELECT nome, preco FROM servicos WHERE usuario_id = :user ORDER BY nome ASC"), 
                {"user": salao_clean}
            )
            rows = res_serv.fetchall()
            if rows:
                servicos = {row[0]: float(row[1]) for row in rows}
    except Exception:
        pass

    # Fallback caso não existam serviços cadastrados ainda
    if not servicos:
        servicos = {"Corte de Cabelo": 25.00, "Barba": 25.00, "Combo (Corte + Barba)": 50.00}
        
    return servicos, whatsapp

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
telefone_dono_param = query_params.get("whats", os.getenv("TELEFONE_DONO", ""))

salao_id_clean = urllib.parse.unquote(str(salao_param)).strip().lower()
nome_salao_formatado = salao_id_clean.replace('_', ' ').replace('-', ' ').title()

# Busca os serviços e o WhatsApp cadastrado diretamente no Supabase
servicos_disponiveis, whatsapp_banco = buscar_dados_salao(salao_id_clean)

# Prioriza o WhatsApp do banco de dados; se não houver, utiliza o da URL/Env
telefone_dono_final = whatsapp_banco if whatsapp_banco else telefone_dono_param

# --- 6. INTERFACE DE AGENDAMENTO DO CLIENTE ---
st.title("✂️ Agendamento Online")
st.write(f"Seja bem-vindo ao sistema de agendamento de **{nome_salao_formatado}**.")

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
                
                data_formatada = data_escolhida.strftime("%d/%m/%Y")
                
                st.success("🎉 **Agendamento salvo com sucesso!**")
                
                st.markdown(
                    f"""
                    ### 📅 Resumo da sua Reserva
                    * **Cliente:** {nome_cliente}
                    * **Data:** {data_formatada}
                    * **Horário:** {hora_limpa}
                    * **Serviço:** {servico_escolhido}
                    """
                )
                
                # --- ENVIAR NOTIFICAÇÃO VIA WHATSAPP PARA O ESTABELECIMENTO ---
                num_dono_limpo = re.sub(r'\D', '', str(telefone_dono_final))
                if num_dono_limpo and not num_dono_limpo.startswith("55") and len(num_dono_limpo) in [10, 11]:
                    num_dono_limpo = f"55{num_dono_limpo}"

                # Mensagem formatada para o WhatsApp
                msg_whatsapp = (
                    f"Olá! Acabei de realizar um agendamento pelo site.\n\n"
                    f"👤 *Cliente:* {nome_cliente}\n"
                    f"📅 *Data:* {data_formatada}\n"
                    f"⏰ *Horário:* {hora_limpa}\n"
                    f"✂️ *Serviço:* {servico_escolhido}"
                )
                msg_encoded = urllib.parse.quote(msg_whatsapp)

                if num_dono_limpo:
                    link_wa = f"https://wa.me/{num_dono_limpo}?text={msg_encoded}"
                else:
                    link_wa = f"https://wa.me/?text={msg_encoded}"

                # --- CARD E BOTÃO PERSONALIZADO DO WHATSAPP (VERDE OFICIAL + ÍCONE SVG) ---
                st.markdown(
                    f"""
                    <div style="
                        background-color: #f0fdf4;
                        border: 2px solid #25D366;
                        border-radius: 12px;
                        padding: 18px;
                        text-align: center;
                        margin-top: 20px;
                        margin-bottom: 20px;
                    ">
                        <p style="
                            color: #166534; 
                            font-size: 16px; 
                            font-weight: 600; 
                            margin-bottom: 12px;
                        ">
                            ⚠️ <b>ÚLTIMO PASSO:</b> Clique no botão abaixo para enviar o comprovante direto para o WhatsApp do estabelecimento e confirmar seu horário.
                        </p>
                        
                        <a href="{link_wa}" target="_blank" style="text-decoration: none;">
                            <div style="
                                background-color: #25D366;
                                color: #FFFFFF;
                                padding: 14px 20px;
                                border-radius: 10px;
                                text-align: center;
                                font-weight: bold;
                                font-size: 18px;
                                box-shadow: 0px 4px 12px rgba(37, 211, 102, 0.45);
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                gap: 10px;
                                cursor: pointer;
                            ">
                                <svg width="26" height="26" viewBox="0 0 24 24" fill="#FFFFFF" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414-.074-.124-.272-.198-.57-.347z"/>
                                    <path d="M12 0C5.373 0 0 5.373 0 12c0 2.119.553 4.11 1.519 5.84L0 24l6.335-1.652C8.016 23.284 9.948 23.858 12 23.858c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.82c-1.802 0-3.567-.484-5.116-1.403l-.367-.218-3.799.992 1.012-3.702-.24-.38C2.536 15.542 2.02 13.808 2.02 12c0-5.503 4.477-9.98 9.98-9.98 5.503 0 9.98 4.477 9.98 9.98 0 5.503-4.477 9.982-9.98 9.982z"/>
                                </svg>
                                <span>Confirmar Agendamento no WhatsApp</span>
                            </div>
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            except Exception as e:
                st.error(f"Ocorreu um erro ao salvar o agendamento: {e}")
