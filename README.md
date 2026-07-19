# Super 12 - Beach Tênis

App em Streamlit para registrar pontos de torneios estilo "Super 12" (jogadores
individuais, duplas sorteadas a cada rodada, ranking por pontos acumulados).

## Como funciona

- **Jogadores**: cadastre os nomes (ideal: múltiplos de 4 — 8, 12, 16...).
- **Gerar Rodada**: sorteia as duplas tentando não repetir parceiros ao longo
  do torneio. Se o número de jogadores não for múltiplo de 4, o app reveza
  quem fica de folga a cada rodada.
- **Registrar Placar**: você digita o placar de cada quadra.
- **Classificação**: soma automaticamente os pontos de cada jogador (o placar
  do time conta para os dois jogadores), com desempate por vitórias e saldo.

Só quem estiver no **modo organizador** (protegido por PIN) vê e edita as
abas de cadastro/sorteio/placar. Quem só tiver o link vê apenas a
**Classificação** — assim dá pra compartilhar o resultado ao vivo sem que
qualquer pessoa mexa nos dados.

⚠️ **Antes de compartilhar o link**, troque o PIN padrão (`1234`) na linha
`ORGANIZER_PIN` no início do `app.py`.

## Rodar localmente (para testar no seu PC)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abre automaticamente no navegador em `http://localhost:8501`.
No celular, na mesma rede Wi-Fi, acesse pelo IP do PC (ex: `http://192.168.0.10:8501`).

## Publicar de graça para acessar de qualquer lugar (Streamlit Community Cloud)

1. Crie uma conta gratuita em https://share.streamlit.io (pode entrar com GitHub).
2. Suba estes arquivos (`app.py` e `requirements.txt`) para um repositório no
   GitHub (pode ser privado).
3. No Streamlit Community Cloud, clique em "New app", selecione o repositório
   e o arquivo `app.py`.
4. Em alguns segundos você recebe uma URL pública (tipo
   `https://seuapp.streamlit.app`) — abre normal no navegador do celular e
   pode "Adicionar à tela inicial" para parecer um app.

## Observação sobre os dados

Os dados ficam na memória da sessão do navegador. Use o botão **"Baixar
backup (JSON)"** na barra lateral de vez em quando (ex: no fim de cada
torneio) para não perder o histórico se a página recarregar.
