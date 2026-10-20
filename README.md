# Agente de vagas

Agente de IA que ajuda a encontrar vagas de emprego com mais precisão.

**Acesse:** (https://agente-vagas.streamlit.app/)

## Como funciona

1. **Perfil:** você envia o currículo em PDF e responde a uma entrevista curta em formato de chat.
2. **Busca:** o agente procura vagas compatíveis com o seu perfil.
3. **Resultados:** cada vaga recebe nota de compatibilidade e de acessibilidade, com o que combina e o que falta, além de uma carta de apresentação sugerida e o link para se candidatar.
4. **Buscas manuais:** links prontos de LinkedIn, Indeed e Gupy para você se candidatar por conta própria.

## Privacidade

- O app **não salva** currículos, respostas nem perfis. Os dados ficam apenas na sessão de cada pessoa e são descartados ao encerrar a visita.
- O texto do currículo e das respostas é enviado à API do Google (Gemini) para ser analisado.
- Evite enviar CPF, RG ou outros documentos pessoais.
- Confira sempre as cartas geradas antes de enviar: a IA pode errar.

## Tecnologias

Python, Streamlit, Google Gemini API e Adzuna API.

## Aviso

Projeto pessoal e experimental. As notas e sugestões são geradas por IA e não garantem contratação.
