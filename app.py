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
        with st.spinner("Montando seu perfil..."):
            montar_perfil()
        st.session_state.entrevista_fim = False
        st.session_state.mensagens = []
        st.session_state.texto_cv = ""
        st.rerun()


# =====================================================
# TELA 2: BUSCAR VAGAS
# =====================================================
def buscar_adzuna(perfil):
    cargos = [perfil["cargo_alvo"]] + perfil.get("cargos_alternativos", [])
    cidade = perfil.get("cidade", "")
    remoto = perfil.get("modalidade") == "remoto"
    vagas = []
    for cargo in cargos[:3]:
        params = {
            "app_id": pegar_chave("ADZUNA_ID"),
            "app_key": pegar_chave("ADZUNA_KEY"),
            "results_per_page": 20,
            "what": cargo + (" remoto" if remoto else ""),
            "max_days_old": 3,
        }
        if not remoto and cidade:
            params["where"] = cidade
        url = "https://api.adzuna.com/v1/api/jobs/br/search/1?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                dados = json.load(r)
        except Exception:
            st.warning(f"Não consegui buscar vagas para '{cargo}' agora.")
            continue
        for v in dados.get("results", []):
            vagas.append({
                "titulo": v.get("title"),
                "empresa": v.get("company", {}).get("display_name"),
                "local": v.get("location", {}).get("display_name"),
                "salario_min": v.get("salary_min"),
                "salario_max": v.get("salary_max"),
                "descricao": v.get("description"),
                "link": v.get("redirect_url"),
            })
    return list({v["link"]: v for v in vagas}.values())


def avaliar(perfil, vagas, barra):
    resultados = []
    TAMANHO_LOTE, MAX_DESC = 5, 1200
    for inicio in range(0, len(vagas), TAMANHO_LOTE):
        lote = vagas[inicio:inicio + TAMANHO_LOTE]
        texto = ""
        for n, v in enumerate(lote):
            texto += f"""
--- VAGA {n} ---
Título: {v['titulo']}
Empresa: {v['empresa']}
Local: {v['local']}
Salário: {v['salario_min']} a {v['salario_max']}
Descrição: {(v.get('descricao') or '')[:MAX_DESC]}
"""
        pedido = f"""
Compare o PERFIL com cada VAGA. Responda SOMENTE com uma lista JSON válida,
um item por vaga, cada item com: vaga (número), nota (0-100, compatibilidade),
acessibilidade (0-100, chance de ser chamado), combina (lista curta),
falta (lista curta), justificativa (uma frase).
Considere salário mínimo, modalidade, cidades aceitas e áreas a evitar.
Se a vaga fere uma regra do perfil, reduza a nota.

PERFIL:
{json.dumps(perfil, ensure_ascii=False)}

VAGAS:
{texto}
"""
        try:
            for av in ler_json(gerar(pedido)):
                n = av.get("vaga")
                if isinstance(n, int) and 0 <= n < len(lote):
                    resultados.append({**lote[n], **av})
        except Exception:
            st.warning("Um lote de vagas deu erro e foi pulado.")
        barra.progress(min((inicio + TAMANHO_LOTE) / len(vagas), 1.0))
        time.sleep(3)
    resultados.sort(key=lambda v: v.get("nota", 0), reverse=True)
    return resultados


if tela == "2. Buscar vagas":
    st.title("Buscar vagas")
    if not st.session_state.perfil:
        st.warning("Primeiro crie seu perfil na etapa 1.")
        st.stop()

    limite = st.slider("Quantas vagas avaliar?", 5, 20, 10, step=5)
    if st.button("🔎 Buscar e avaliar vagas", type="primary"):
        with st.spinner("Buscando vagas..."):
            vagas = buscar_adzuna(st.session_state.perfil)[:limite]
        if not vagas:
            st.warning("Nenhuma vaga encontrada agora. Use os links manuais na etapa 3.")
        else:
            st.write(f"{len(vagas)} vagas encontradas. Dando nota...")
            barra = st.progress(0.0)
            st.session_state.vagas = avaliar(st.session_state.perfil, vagas, barra)
            st.success("Pronto! Veja os resultados na etapa 3.")


# =====================================================
# TELA 3: RESULTADOS
# =====================================================
if tela == "3. Resultados":
    st.title("Resultados")
    if not st.session_state.perfil:
        st.warning("Primeiro crie seu perfil na etapa 1.")
        st.stop()

    perfil = st.session_state.perfil
    nota_min = st.slider("Nota mínima", 0, 100, 60)
    vagas = [v for v in st.session_state.vagas if v.get("nota", 0) >= nota_min]

    if not vagas:
        st.info("Nenhuma vaga para mostrar. Rode a etapa 2 ou baixe a nota mínima.")
    else:
        mais_acessivel = max(vagas, key=lambda v: v.get("acessibilidade", 0))
        c1, c2, c3 = st.columns(3)
        c1.metric("Vagas", len(vagas))
        c2.metric("Maior compatibilidade", vagas[0].get("nota"))
        c3.metric("Maior acessibilidade", mais_acessivel.get("acessibilidade"))

        for i, v in enumerate(vagas):
            with st.container(border=True):
                tag = ""
                if i == 0:
                    tag = "⭐ Mais compatível · "
                elif v is mais_acessivel:
                    tag = "🎯 Mais acessível · "
                st.subheader(f"{tag}{v['titulo']}")
                st.caption(f"{v['empresa']} · {v['local']}")
                a, b = st.columns(2)
                a.metric("Compatibilidade", v.get("nota"))
                b.metric("Acessibilidade", v.get("acessibilidade"))
                st.write(f"*{v.get('justificativa', '')}*")
                x, y = st.columns(2)
                x.write("**Combina**")
                for item in v.get("combina", []):
                    x.write(f"✅ {item}")
                y.write("**Falta**")
                for item in v.get("falta", []):
                    y.write(f"⚠️ {item}")

                chave_carta = f"carta_{i}"
                if st.button("✉️ Gerar carta de apresentação", key=f"btn_{i}"):
                    pedido = f"""
Escreva uma carta de apresentação curta (máximo 150 palavras) em português
do Brasil, tom profissional e natural, para o candidato se candidatar à vaga.
Use SOMENTE informações do perfil. Não invente experiências, empresas,
cursos ou números. Sem assinatura. Responda só com o texto da carta.

PERFIL:
{json.dumps(perfil, ensure_ascii=False)}

VAGA:
Título: {v['titulo']}
Empresa: {v['empresa']}
Descrição: {(v.get('descricao') or '')[:1200]}
"""
                    with st.spinner("Escrevendo..."):
                        st.session_state[chave_carta] = gerar(pedido)
                if chave_carta in st.session_state:
                    st.text_area("Carta (confira antes de enviar)",
                                 st.session_state[chave_carta], height=220,
                                 key=f"area_{i}")

                st.link_button("Ver vaga e se candidatar", v["link"])

    st.divider()
    st.subheader("Buscas manuais (LinkedIn, Indeed, Gupy)")
    cargos = [perfil["cargo_alvo"]] + perfil.get("cargos_alternativos", [])
    remoto = perfil.get("modalidade") == "remoto"
    local = "Brasil" if remoto else perfil.get("cidade", "")
    for cargo in cargos[:3]:
        q, l = urllib.parse.quote(cargo), urllib.parse.quote(local)
        linkedin = f"https://www.linkedin.com/jobs/search/?keywords={q}&location={l}&f_TPR=r86400"
        if remoto:
            linkedin += "&f_WT=2"
        st.write(f"**{cargo}**")
        c1, c2, c3 = st.columns(3)
        c1.link_button("LinkedIn", linkedin, key=f"li_{cargo}")
        c2.link_button("Indeed", f"https://br.indeed.com/jobs?q={q}&l={l}&fromage=1", key=f"in_{cargo}")
        c3.link_button("Gupy", f"https://portal.gupy.io/job-search/term={q}", key=f"gu_{cargo}")
