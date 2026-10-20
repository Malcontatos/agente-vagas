import os
import json
import time
import urllib.parse
import urllib.request
from datetime import date

import streamlit as st
from pypdf import PdfReader
from google import genai

MODELO = "gemini-3.8-flash"

# ---------- Limites de uso (ajuste conforme seu plano) ----------
LIMITE_SESSAO = 30        # chamadas de IA por pessoa (por visita)
LIMITE_GLOBAL_DIA = 200   # chamadas de IA por dia, somando todo mundo

st.set_page_config(page_title="Agente de Vagas", page_icon="💼")


# ---------- Chaves (Secrets na nuvem, variáveis no seu PC) ----------
def pegar_chave(nome):
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return os.environ.get(nome)


for chave in ["GEMINI_API_KEY", "ADZUNA_ID", "ADZUNA_KEY"]:
    if not pegar_chave(chave):
        st.error(f"Falta a chave {chave}. No PC, use o setx e reinicie o VS Code. "
                 "Na nuvem, coloque nos Secrets.")
        st.stop()

cliente = genai.Client(api_key=pegar_chave("GEMINI_API_KEY"))


# ---------- Contador global (só números, nenhum dado de currículo) ----------
@st.cache_resource
def contador_global():
    return {"dia": date.today(), "n": 0}


def registrar_uso():
    """Conta uma chamada de IA. Para o app se algum limite foi atingido."""
    g = contador_global()
    if g["dia"] != date.today():
        g["dia"], g["n"] = date.today(), 0
    if g["n"] >= LIMITE_GLOBAL_DIA:
        st.error("O site atingiu o limite de uso de hoje. Volte amanhã! 🙏")
        st.stop()
    if st.session_state.usos >= LIMITE_SESSAO:
        st.error("Você atingiu o limite de usos desta visita. "
                 "Use os links de busca manual ou volte amanhã.")
        st.stop()
    g["n"] += 1
    st.session_state.usos += 1


def gerar(pedido, instrucoes=None, tentativas=5):
    """Chama a IA e tenta de novo se o Google estiver ocupado."""
    registrar_uso()
    espera = 10
    for t in range(1, tentativas + 1):
        try:
            config = {"system_instruction": instrucoes} if instrucoes else None
            return cliente.models.generate_content(
                model=MODELO, contents=pedido, config=config
            ).text.strip()
        except Exception as erro:
            if "503" in str(erro) and t < tentativas:
                time.sleep(espera)
                espera *= 2
            else:
                raise


def ler_json(texto):
    return json.loads(texto.replace("```json", "").replace("```", "").strip())


# ---------- Estado (memória só desta pessoa) ----------
padrao = {
    "perfil": None,
    "vagas": [],
    "texto_cv": "",
    "arquivo_id": None,
    "mensagens": [],
    "entrevista_fim": False,
    "usos": 0,
}
for k, v in padrao.items():
    st.session_state.setdefault(k, v)

# ---------- Menu ----------
st.sidebar.title("💼 Agente de Vagas")
tela = st.sidebar.radio("Etapas", ["1. Perfil", "2. Buscar vagas", "3. Resultados"])
st.sidebar.caption(f"Usos da IA nesta visita: {st.session_state.usos}/{LIMITE_SESSAO}")
if st.sidebar.button("🗑️ Apagar meus dados"):
    st.session_state.clear()
    st.rerun()

st.info(
    "🔒 **Privacidade:** seu currículo e suas respostas são usados só durante esta "
    "visita para montar seu perfil e avaliar vagas. Este site não os salva e eles "
    "são descartados ao encerrar a visita. O texto é enviado ao Google (Gemini) "
    "para ser analisado. Evite enviar CPF, RG ou outros documentos."
)


# =====================================================
# TELA 1: PERFIL
# =====================================================
def instrucoes_entrevista():
    return f"""
Você é um entrevistador de carreira simpático. Seu objetivo é descobrir
o que a pessoa busca em uma vaga de emprego.
Regras:
- Faça UMA pergunta por vez, curta e simples.
- Descubra o primeiro nome da pessoa no currículo e use-o de vez em quando,
  de forma natural, sem exagerar.
- Use o currículo abaixo para não perguntar o que já está lá.
- Descubra: cargo desejado, remoto/híbrido/presencial, cidades aceitas,
  salário mínimo, tipo de contrato (CLT, PJ), áreas ou empresas a evitar,
  o que valoriza e disponibilidade.
- Faça no máximo 8 perguntas.
- Quando tiver informação suficiente, escreva apenas: FIM

CURRÍCULO:
{st.session_state.texto_cv}
"""


def proxima_fala():
    contents = [{"role": "user", "parts": [{"text": "Comece a entrevista."}]}]
    for m in st.session_state.mensagens:
        papel = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": papel, "parts": [{"text": m["content"]}]})
    return gerar(contents, instrucoes_entrevista())


def montar_perfil():
    conversa = "\n".join(
        f"{'Agente' if m['role'] == 'assistant' else 'Pessoa'}: {m['content']}"
        for m in st.session_state.mensagens
    )
    pedido = f"""
Com base no currículo e na entrevista abaixo, responda SOMENTE com um
JSON válido, sem explicações, com estes campos:
nome (primeiro nome da pessoa, como aparece no currículo), cargo_alvo,
cargos_alternativos (lista), senioridade, habilidades (lista),
idiomas (lista), cidade, modalidade (remoto, hibrido, presencial ou qualquer),
cidades_aceitas (lista), salario_minimo (número ou null), tipo_contrato (lista),
evitar (lista), prioridades (lista), resumo (2 frases).

CURRÍCULO:
{st.session_state.texto_cv}

ENTREVISTA:
{conversa}
"""
    st.session_state.perfil = ler_json(gerar(pedido))


if tela == "1. Perfil":
    st.title("Seu perfil")

    if st.session_state.perfil and not st.session_state.mensagens:
        p = st.session_state.perfil
        nome = p.get("nome") or ""
        st.success(f"Perfil pronto{', ' + nome if nome else ''}! "
                   "Pode ir para a etapa 2, ou refazer abaixo.")
        st.write(f"**Cargo:** {p.get('cargo_alvo')} ({p.get('senioridade')})")
        st.write(f"**Modalidade:** {p.get('modalidade')} · **Cidade:** {p.get('cidade')}")
        st.write(f"**Resumo:** {p.get('resumo')}")
        with st.expander("Ver perfil completo"):
            st.json(p)
        st.divider()
        st.subheader("Refazer perfil")

    arquivo = st.file_uploader("Envie seu currículo (PDF)", type="pdf")
    if arquivo:
        id_arquivo = f"{arquivo.name}-{arquivo.size}"
        # só lê o PDF quando é um arquivo novo (evita recomeçar a entrevista)
        if id_arquivo != st.session_state.arquivo_id:
            try:
                leitor = PdfReader(arquivo)
                texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
            except Exception:
                texto = ""
            if len(texto.strip()) < 50:
                st.error("Não consegui ler texto desse PDF (pode ser imagem escaneada).")
            else:
                st.session_state.texto_cv = texto
                st.session_state.arquivo_id = id_arquivo
                st.session_state.mensagens = []
                st.session_state.entrevista_fim = False

    if st.session_state.texto_cv and not st.session_state.entrevista_fim:
        st.info("Currículo lido. Responda as perguntas abaixo.")

        if not st.session_state.mensagens:
            with st.spinner("Preparando a primeira pergunta..."):
                st.session_state.mensagens.append(
                    {"role": "assistant", "content": proxima_fala()}
                )

        for m in st.session_state.mensagens:
            with st.chat_message(m["role"]):
                st.write(m["content"])

        resposta = st.chat_input("Digite sua resposta")
        if resposta:
            st.session_state.mensagens.append({"role": "user", "content": resposta})
            with st.spinner("Pensando..."):
                fala = proxima_fala()
            if "FIM" in fala[:10]:
                st.session_state.entrevista_fim = True
            else:
                st.session_state.mensagens.append({"role": "assistant", "content": fala})
            st.rerun()

        if len(st.session_state.mensagens) >= 4:
            if st.button("Encerrar entrevista e gerar perfil"):
                st.session_state.entrevista_fim = True
                st.rerun()

    if st.session_state.entrevista_fim:
