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
    "08:00", "09:00", "10:00",
    "11:00", "13:00", "14:00", 
    "15:00", "16:00", "17:00", 
    "18:00", "19:00"
]

# --- 4. FUNÇÕES DE SUPORTE E FORMATADORES ---
def formatar_whatsapp_dono(numero_bruto):
    """Limpa e formata o número do dono para garantir abertura direta no WhatsApp."""
    if not numero_bruto:
        return ""
    
    num_limpo = re.sub(r'\D', '', str(numero_bruto)).lstrip('0')
    
    if not num_limpo:
        return ""
        
    if len(num_limpo) in [10, 11]:
        num_limpo = f"55{num_limpo}"
        
    return num_limpo

def obter_colunas_tabela(tabela_nome):
    """Retorna a lista de colunas reais existentes em uma tabela do banco de dados."""
    try:
        with engine.connect() as conn:
            res = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :tbl"),
                {"tbl": tabela_nome}
            ).fetchall()
            return [r[0].lower() for r in res]
    except Exception:
        return []

# --- 5. BUSCA INTELIGENTE E DINÂMICA DO SALÃO ---
def buscar_dados_salao(salao_id):
    """Busca os serviços e o telefone do salão cadastrado, adaptando-se às colunas reais do banco."""
    if not salao_id:
        return {}, ""

    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    salao_busca_normalizada = re.sub(r'[^a-z0-9]', '', salao_clean)

    servicos = {}
    whatsapp = ""

    cols_usuarios = obter_colunas_tabela("usuarios")

    col_telefone = None
    for c in ["whatsapp", "telefone", "celular", "contato", "zap", "phone"]:
        if c in cols_usuarios:
            col_telefone = c
            break

    cols_id = [c for c in ["usuario_id", "usuario", "login", "username", "nome_salao", "nome", "slug", "email", "id"] if c in cols_usuarios]

    if col_telefone and cols_id:
        condicoes = []
        for col in cols_id:
            condicoes.append(f"REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE({col}::text, ''))), '_', ''), '-', ''), ' ', '') = :busca")
            condicoes.append(f"LOWER(TRIM(COALESCE({col}::text, ''))) = :raw")

        sql_user = f"SELECT {col_telefone} FROM usuarios WHERE {' OR '.join(condicoes)} LIMIT 1"

        try:
            with engine.connect() as conn:
                res = conn.execute(text(sql_user), {"busca": salao_busca_normalizada, "raw": salao_clean}).fetchone()
                if res and res[0]:
                    whatsapp = str(res[0])
        except Exception:
            pass

        if not whatsapp:
            condicoes_like = [f"LOWER({col}::text) LIKE :like" for col in cols_id]
            sql_like = f"SELECT {col_telefone} FROM usuarios WHERE {' OR '.join(condicoes_like)} LIMIT 1"
            try:
                with engine.connect() as conn:
                    res_like = conn.execute(text(sql_like), {"like": f"%{salao_busca_normalizada}%"}).fetchone()
                    if res_like and res_like[0]:
                        whatsapp = str(res_like[0])
            except Exception:
                pass

    cols_servicos = obter_colunas_tabela("servicos")
    cols_serv_id = [c for c in ["usuario_id", "usuario", "login", "username", "nome_salao", "salao_id"] if c in cols_servicos]

    if cols_servicos and "nome" in cols_servicos and "preco" in cols_servicos and cols_serv_id:
        condicoes_serv = [f"REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE({c}::text, ''))), '_', ''), '-', ''), ' ', '') = :busca" for c in cols_serv_id]
        sql_serv = f"SELECT nome, preco FROM servicos WHERE {' OR '.join(condicoes_serv)} ORDER BY nome ASC"
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql_serv), {"busca": salao_busca_normalizada}).fetchall()
                if rows:
                    servicos = {r[0]: float(r[1]) for r in rows}
        except Exception:
            pass

    if not servicos:
        servicos = {"Corte de Cabelo": 30.00, "Barba": 30.00, "Combo (Corte + Barba)": 50.00}

    return servicos, whatsapp

def buscar_horarios_ocupados(salao_id, data_str):
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    salao_busca_normalizada = re.sub(r'[^a-z0-9]', '', salao_clean)
    cols_agend = obter_colunas_tabela("agendamentos")
    cols_id = [c for c in ["usuario_id", "usuario", "salao_id"] if c in cols_agend]

    if not cols_id:
        return []

    condicoes = [f"REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE({c}::text, ''))), '_', ''), '-', ''), ' ', '') = :busca" for c in cols_id]
    sql = f"SELECT hora FROM agendamentos WHERE ({' OR '.join(condicoes)}) AND data = :dt"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), {"busca": salao_busca_normalizada, "dt": data_str})
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

# --- NOVAS FUNÇÕES PARA O CANCELAMENTO DE AGENDAMENTOS ---
def buscar_agendamentos_cliente(salao_id, contato_cliente):
    """Busca agendamentos ativos a partir do WhatsApp informado pelo cliente."""
    salao_clean = urllib.parse.unquote(str(salao_id)).strip().lower()
    salao_busca_normalizada = re.sub(r'[^a-z0-9]', '', salao_clean)
    
    num_limpo = re.sub(r'\D', '', str(contato_cliente))
    if not num_limpo or len(num_limpo) < 8:
        return []

    cols_agend = obter_colunas_tabela("agendamentos")
    cols_id = [c for c in ["usuario_id", "usuario", "salao_id"] if c in cols_agend]
    if not cols_id:
        return []

    condicoes_salao = [f"REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE({c}::text, ''))), '_', ''), '-', ''), ' ', '') = :busca" for c in cols_id]
    
    agora_br = datetime.now(TZ_BR)
    hoje_str = agora_br.strftime("%Y-%m-%d")

    # Tenta buscar os campos principais
    sql = f"""
        SELECT id, cliente_nome, servico_nome, data, hora 
        FROM agendamentos 
        WHERE ({' OR '.join(condicoes_salao)}) 
        AND (
            REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cliente_contato, ''), ' ', ''), '-', ''), '(', ''), ')', '') LIKE :tel
            OR REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cliente_telefone, ''), ' ', ''), '-', ''), '(', ''), ')', '') LIKE :tel
        )
        AND data >= :hoje
        ORDER BY data ASC, hora ASC
    """
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql), {
                "busca": salao_busca_normalizada,
                "tel": f"%{num_limpo}%",
                "hoje": hoje_str
            }).fetchall()
            return res
    except Exception:
        return []

def cancelar_agendamento_por_id(agendamento_id):
    """Remove o agendamento diretamente no banco pelo ID."""
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM agendamentos WHERE id = :id"), {"id": agendamento_id})
        return True
    except Exception:
        return False

# --- 6. EXTRAÇÃO DINÂMICA DO PARÂMETRO DA URL ---
query_params = st.query_params

salao_raw = query_params.get("salao", None)
if isinstance(salao_raw, list):
    salao_raw = salao_raw[0] if salao_raw else None

if not salao_raw:
    st.error("❌ **Link incompleto!** Por favor, acesse o sistema através do link exclusivo do seu salão.")
    st.info("Exemplo de link correto: `https://seu-sistema.com/?salao=nome_do_salao`")
    st.stop()

salao_id_clean = urllib.parse.unquote(str(salao_raw)).strip().lower()
nome_salao_formatado = salao_id_clean.replace('_', ' ').replace('-', ' ').title()

# Consulta os dados reais do salão no banco
servicos_disponiveis, whatsapp_banco = buscar_dados_salao(salao_id_clean)
telefone_dono_final = formatar_whatsapp_dono(whatsapp_banco)

# --- 7. INTERFACE PRINCIPAL NAVEGÁVEL EM ABAS ---
st.title("✂️ Agendamento Online")
st.write(f"Seja bem-vindo ao sistema de agendamento de **{nome_salao_formatado}**.")

tab_agendar, tab_cancelar = st.tabs(["📅 Novo Agendamento", "❌ Cancelar / Meus Agendamentos"])

# ==========================================
# ABA 1: NOVO AGENDAMENTO
# ==========================================
with tab_agendar:
    agora_br = datetime.now(TZ_BR)
    hoje_str = agora_br.strftime("%Y-%m-%d")
    hora_atual_str = agora_br.strftime("%H:%M")

    data_escolhida = st.date_input("Escolha o Dia do Agendamento:", min_value=agora_br.date(), key="data_agendamento")
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
                    
                    msg_whatsapp = (
                        f"Olá! Acabei de realizar um agendamento pelo site.\n\n"
                        f"👤 *Cliente:* {nome_cliente}\n"
                        f"📅 *Data:* {data_formatada}\n"
                        f"⏰ *Horário:* {hora_limpa}\n"
                        f"✂️ *Serviço:* {servico_escolhido}"
                    )
                    msg_encoded = urllib.parse.quote(msg_whatsapp)

                    if telefone_dono_final:
                        link_wa = f"https://wa.me/{telefone_dono_final}?text={msg_encoded}"
                    else:
                        link_wa = f"https://wa.me/?text={msg_encoded}"
                        st.warning(f"⚠️ **Aviso ao Administrador:** O WhatsApp do salão **'{salao_id_clean}'** não foi encontrado no banco de dados.")

                    html_botao = f"""<div style="background-color: #f0fdf4; border: 2px solid #25D366; border-radius: 12px; padding: 18px; text-align: center; margin-top: 20px; margin-bottom: 20px;">
<p style="color: #166534; font-size: 16px; font-weight: 600; margin-bottom: 12px;">⚠️ <b>ÚLTIMO PASSO:</b> Clique no botão abaixo para enviar a confirmação direta para o WhatsApp do salão.</p>
<a href="{link_wa}" target="_blank" style="text-decoration: none;">
<div style="background-color: #25D366; color: #FFFFFF; padding: 14px 20px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 18px; box-shadow: 0px 4px 12px rgba(37, 211, 102, 0.45); display: flex; align-items: center; justify-content: center; gap: 10px; cursor: pointer;">
<svg width="26" height="26" viewBox="0 0 24 24" fill="#FFFFFF" xmlns="http://www.w3.org/2000/svg">
<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414-.074-.124-.272-.198-.57-.347z"/>
<path d="M12 0C5.373 0 0 5.373 0 12c0 2.119.553 4.11 1.519 5.84L0 24l6.335-1.652C8.016 23.284 9.948 23.858 12 23.858c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.82c-1.802 0-3.567-.484-5.116-1.403l-.367-.218-3.799.992 1.012-3.702-.24-.38C2.536 15.542 2.02 13.808 2.02 12c0-5.503 4.477-9.98 9.98-9.98 5.503 0 9.98 4.477 9.98 9.98 0 5.503-4.477 9.982-9.98 9.982z"/>
</svg>
<span>Enviar Confirmação no WhatsApp</span>
</div>
</a>
</div>"""

                    st.markdown(html_botao, unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao salvar o agendamento: {e}")

# ==========================================
# ABA 2: CANCELAR AGENDAMENTO
# ==========================================
with tab_cancelar:
    st.subheader("🔎 Localizar e Cancelar Agendamento")
    st.write("Surgiu algum imprevisto? Digite abaixo o número de telefone/WhatsApp cadastrado para buscar e cancelar seus horários marcados.")

    tel_busca = st.text_input("Digite o seu WhatsApp cadastrado (com DDD):", key="tel_cancelar")
    
    if tel_busca:
        meus_agendamentos = buscar_agendamentos_cliente(salao_id_clean, tel_busca)
        
        if meus_agendamentos:
            st.success(f"Encontramos **{len(meus_agendamentos)}** agendamento(s) ativo(s):")
            
            for item in meus_agendamentos:
                ag_id, cliente_n, servico_n, data_ag, hora_ag = item[0], item[1], item[2], item[3], item[4]
                
                # Formata data para dd/mm/yyyy
                data_dt = datetime.strptime(str(data_ag), "%Y-%m-%d") if isinstance(data_ag, str) else data_ag
                data_formatada = data_dt.strftime("%d/%m/%Y")
                
                with st.expander(f"📌 {data_formatada} às {hora_ag} - {servico_n}", expanded=True):
                    st.write(f"**Cliente:** {cliente_n}")
                    st.write(f"**Serviço:** {servico_n}")
                    st.write(f"**Data e Hora:** {data_formatada} às {hora_ag}")
                    
                    if st.button(f"🗑️ Confirmar Cancelamento", key=f"btn_del_{ag_id}", type="primary"):
                        if cancelar_agendamento_por_id(ag_id):
                            st.toast("✅ Agendamento cancelado com sucesso!", icon="🎉")
                            st.success("Seu horário foi cancelado e o horário já está liberado novamente.")
                            st.rerun()
                        else:
                            st.error("Erro ao tentar cancelar o agendamento. Tente novamente.")
        else:
            st.info("Nenhum agendamento futuro foi encontrado com esse número para este salão.")
