import io
import json
import os
import random
import threading
from datetime import datetime, date

import pandas as pd
import streamlit as st
from PIL import Image as PILImage
from reportlab.graphics.shapes import Circle, Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak,
                                 PageTemplate, Paragraph, Spacer, Table, TableStyle)
from streamlit_autorefresh import st_autorefresh

# Banner do cabeçalho do PDF (mesma pasta do app.py). Se o arquivo não
# existir (ex: esqueceu de subir pro GitHub), o PDF usa um título em
# texto no lugar, sem quebrar.
# Banner do cabeçalho do PDF (mesma pasta do app.py). Aceita qualquer uma
# dessas extensões — não precisa ser exatamente .jpg — e se nenhum arquivo
# for encontrado, o PDF usa um título em texto no lugar, sem quebrar.
def _localizar_banner():
    pasta = os.path.dirname(os.path.abspath(__file__))
    nome_base = "banner_arena_polese"
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        caminho = os.path.join(pasta, nome_base + ext)
        if os.path.exists(caminho):
            return caminho
    return None


BANNER_PATH = _localizar_banner()

# ============================================================
# CONFIGURAÇÃO
# ============================================================
st.set_page_config(page_title="Super Arena Polese", page_icon="🎾", layout="centered")

# Troque esse PIN antes de compartilhar o link do app!
ORGANIZER_PIN = "1234"

OURO = colors.HexColor("#D4AF37")
OURO_BORDA = colors.HexColor("#8A6D1F")
PRATA = colors.HexColor("#A8A9AD")
PRATA_BORDA = colors.HexColor("#6E6F72")
BRONZE = colors.HexColor("#AD8A56")
BRONZE_BORDA = colors.HexColor("#7A5F3B")

# ============================================================
# ESTADO COMPARTILHADO
# Guardado com st.cache_resource: um único objeto vivo na memória
# do servidor, visto por TODO MUNDO que acessa o app (não é por
# navegador). É isso que permite compartilhar o link e todo mundo
# ver o mesmo torneio ao vivo.
# ============================================================
@st.cache_resource
def get_shared_state():
    return {
        "players": [],
        "schedule": None,
        "rounds": [],
        "tournament_date": date.today(),
        "lock": threading.Lock(),
    }


shared = get_shared_state()

# is_organizer fica em session_state (por navegador/pessoa) de propósito:
# cada visitante decide individualmente se está logado como organizador.
if "is_organizer" not in st.session_state:
    st.session_state.is_organizer = False


# ============================================================
# GERAÇÃO DO CALENDÁRIO COMPLETO (método do círculo)
# Garante que cada dupla de jogadores forma parceria
# exatamente uma vez ao longo de todo o torneio.
# ============================================================
def gerar_calendario_completo(players):
    lista = players[:]
    if len(lista) % 2 == 1:
        lista.append(None)  # jogador fantasma (bye)
    n = len(lista)
    fixed = lista[0]
    rot = lista[1:]
    rounds_pairs = []
    for _ in range(n - 1):
        current = [fixed] + rot
        pares = []
        for i in range(n // 2):
            a, b = current[i], current[n - 1 - i]
            if a is not None and b is not None:
                pares.append(sorted([a, b]))
        rounds_pairs.append(pares)
        rot = [rot[-1]] + rot[:-1]
    return rounds_pairs


def montar_partidas_e_folgas(players, pares):
    """A partir das duplas previstas para a rodada, monta as partidas
    (2 duplas por quadra) e identifica quem fica de folga."""
    pares = [p[:] for p in pares]
    random.shuffle(pares)

    jogam = set()
    for d in pares:
        jogam.update(d)
    folgantes = [p for p in players if p not in jogam]  # pegaram o "bye" do calendário

    partidas = []
    i = 0
    while i < len(pares) - 1:
        partidas.append({
            "quadra": len(partidas) + 1,
            "time1": pares[i],
            "time2": pares[i + 1],
            "placar1": None,
            "placar2": None,
        })
        i += 2
    if i == len(pares) - 1:
        folgantes += pares[i]  # dupla sem adversário nessa rodada

    return partidas, folgantes


# ============================================================
# CÁLCULO DE CLASSIFICAÇÃO
# ============================================================
def calcular_classificacao():
    stats = {p: {"pontos": 0, "vitorias": 0, "derrotas": 0, "jogos": 0, "saldo": 0,
                  "melhor_rodada": 0, "folgas": 0}
              for p in shared["players"]}

    for rodada in shared["rounds"]:
        for p in rodada.get("folgantes", []):
            if p in stats:
                stats[p]["folgas"] += 1
        for m in rodada["partidas"]:
            if m["placar1"] is None or m["placar2"] is None:
                continue
            s1, s2 = m["placar1"], m["placar2"]
            for p in m["time1"]:
                if p not in stats:
                    continue
                stats[p]["pontos"] += s1
                stats[p]["jogos"] += 1
                stats[p]["saldo"] += (s1 - s2)
                stats[p]["vitorias"] += 1 if s1 > s2 else 0
                stats[p]["derrotas"] += 1 if s1 < s2 else 0
                stats[p]["melhor_rodada"] = max(stats[p]["melhor_rodada"], s1)
            for p in m["time2"]:
                if p not in stats:
                    continue
                stats[p]["pontos"] += s2
                stats[p]["jogos"] += 1
                stats[p]["saldo"] += (s2 - s1)
                stats[p]["vitorias"] += 1 if s2 > s1 else 0
                stats[p]["derrotas"] += 1 if s2 < s1 else 0
                stats[p]["melhor_rodada"] = max(stats[p]["melhor_rodada"], s2)

    df = pd.DataFrame.from_dict(stats, orient="index")
    df.index.name = "Jogador"
    df = df.sort_values(by=["pontos", "vitorias", "saldo", "melhor_rodada"], ascending=False)

    # Ranking denso: quem empata em TODOS os critérios (pontos, vitórias,
    # saldo e melhor rodada) fica na MESMA posição, mas a posição seguinte
    # sempre avança de 1 em 1 (ex: 1, 2, 2, 3, 4, 5...) — não pula números
    # por causa do empate.
    posicoes = []
    chave_anterior = None
    pos_atual = 0
    for row in df.itertuples():
        chave = (row.pontos, row.vitorias, row.saldo, row.melhor_rodada)
        if chave != chave_anterior:
            pos_atual += 1
            chave_anterior = chave
        posicoes.append(pos_atual)
    df.insert(0, "Pos", posicoes)
    return df


def montar_matriz_pontos_por_rodada():
    """Para cada jogador (ordem alfabética), lista os pontos conquistados em
    cada rodada (None se ele estava de folga ou a rodada ainda não tem
    placar), mais total de pontos, vitórias e derrotas."""
    n_rodadas = len(shared["rounds"])
    jogadores = sorted(shared["players"])
    linhas = []
    for jogador in jogadores:
        pontos_por_rodada = []
        total = 0
        vitorias = 0
        derrotas = 0
        for rodada in shared["rounds"]:
            pontos_rodada = None
            for m in rodada["partidas"]:
                if m["placar1"] is None or m["placar2"] is None:
                    continue
                if jogador in m["time1"]:
                    pontos_rodada = m["placar1"]
                    vitorias += 1 if m["placar1"] > m["placar2"] else 0
                    derrotas += 1 if m["placar1"] < m["placar2"] else 0
                    break
                elif jogador in m["time2"]:
                    pontos_rodada = m["placar2"]
                    vitorias += 1 if m["placar2"] > m["placar1"] else 0
                    derrotas += 1 if m["placar2"] < m["placar1"] else 0
                    break
            if pontos_rodada is not None:
                total += pontos_rodada
            pontos_por_rodada.append(pontos_rodada)
        linhas.append({
            "jogador": jogador, "pontos_por_rodada": pontos_por_rodada,
            "total": total, "vitorias": vitorias, "derrotas": derrotas,
        })
    return linhas, n_rodadas


def montar_tabela_historico():
    linhas = []
    for i, rodada in enumerate(shared["rounds"], start=1):
        for m in rodada["partidas"]:
            if m["placar1"] is not None and m["placar2"] is not None:
                placar = f"{m['placar1']} x {m['placar2']}"
            else:
                placar = "—"
            linhas.append({
                "Rodada": i,
                "Quadra": m["quadra"],
                "Dupla 1": " / ".join(m["time1"]),
                "Dupla 2": " / ".join(m["time2"]),
                "Placar": placar,
            })
        folgantes = rodada.get("folgantes", [])
        if folgantes:
            linhas.append({
                "Rodada": i, "Quadra": "—",
                "Dupla 1": "🪑 Folga: " + ", ".join(folgantes),
                "Dupla 2": "", "Placar": "",
            })
    return pd.DataFrame(linhas)


# ============================================================
# EXPORTAÇÃO EM PDF DA CLASSIFICAÇÃO (pódio + tabela + histórico)
# ============================================================
def _medalha(numero, cor_fundo, cor_borda, tamanho=1.5 * cm):
    d = Drawing(tamanho, tamanho)
    d.add(Circle(tamanho / 2, tamanho / 2, tamanho / 2 - 2,
                  fillColor=cor_fundo, strokeColor=cor_borda, strokeWidth=2.2))
    d.add(String(tamanho / 2, tamanho / 2 - 5.5, str(numero), fontSize=17,
                  fillColor=colors.white, textAnchor="middle", fontName="Helvetica-Bold"))
    return d


def _coluna_podio(numero, nomes, pontos, cor, cor_borda, altura_barra_cm, largura_cm=5.0):
    styles = getSampleStyleSheet()
    tamanho_fonte = 12 if len(nomes) <= 1 else (10 if len(nomes) <= 3 else 9)
    nome_style = ParagraphStyle("nome", parent=styles["Normal"], alignment=TA_CENTER,
                                 fontName="Helvetica-Bold", fontSize=tamanho_fonte, leading=tamanho_fonte + 2,
                                 spaceBefore=4, spaceAfter=2)
    pts_style = ParagraphStyle("pts", parent=styles["Normal"], alignment=TA_CENTER,
                                fontName="Helvetica-Bold", fontSize=11, textColor=colors.white)

    barra = Table([[Paragraph(f"{pontos} pts", pts_style)]],
                   colWidths=[largura_cm * cm], rowHeights=[altura_barra_cm * cm])
    barra.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.75, cor_borda),
    ]))

    texto_nomes = "<br/>".join(nomes)
    conteudo = [[_medalha(numero, cor, cor_borda)], [Paragraph(texto_nomes, nome_style)], [barra]]
    col = Table(conteudo, colWidths=[largura_cm * cm])
    col.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return col


def gerar_pdf_classificacao(df, data_torneio_str):
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4,
                           topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                           leftMargin=1.5 * cm, rightMargin=1.5 * cm)

    frame_retrato = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="retrato")
    largura_pais, altura_pais = landscape(A4)
    margem_pais = 1.3 * cm
    frame_paisagem = Frame(margem_pais, margem_pais, largura_pais - 2 * margem_pais,
                            altura_pais - 2 * margem_pais, id="paisagem")
    doc.addPageTemplates([
        PageTemplate(id="Retrato", frames=[frame_retrato], pagesize=A4),
        PageTemplate(id="Paisagem", frames=[frame_paisagem], pagesize=landscape(A4)),
    ])

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle("titulo", parent=styles["Title"], fontSize=20, spaceAfter=2)
    autoria_style = ParagraphStyle("autoria", parent=styles["Normal"], fontSize=8,
                                    textColor=colors.HexColor("#BBBBBB"), spaceAfter=10)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=colors.grey)

    story = []
    if BANNER_PATH:
        with PILImage.open(BANNER_PATH) as im:
            largura_px, altura_px = im.size
        proporcao = altura_px / largura_px
        largura_banner = doc.width
        altura_banner = largura_banner * proporcao
        story.append(Image(BANNER_PATH, width=largura_banner, height=altura_banner))
        story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("Super Arena Polese", titulo_style))
    story.append(Paragraph("desenvolvido por Amanda Brandes, 2026", autoria_style))
    story.append(Paragraph("Classificação Geral", styles["Heading2"]))
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    story.append(Paragraph(f"Data do torneio: {data_torneio_str}", sub_style))
    story.append(Paragraph(f"PDF gerado em: {agora}", sub_style))
    story.append(Spacer(1, 26))

    # PÓDIO (alturas em degrau: 1º > 2º > 3º) com medalhas numeradas.
    # Jogadores empatados na mesma posição aparecem juntos no mesmo bloco.
    df_indexado = df.reset_index()
    posicoes_distintas = sorted(df_indexado["Pos"].unique())[:3]
    if posicoes_distintas:
        specs = [
            (OURO, OURO_BORDA, 3.6),
            (PRATA, PRATA_BORDA, 2.6),
            (BRONZE, BRONZE_BORDA, 1.8),
        ]
        blocos = [None, None, None]
        for i, pos_valor in enumerate(posicoes_distintas):
            grupo = df_indexado[df_indexado["Pos"] == pos_valor]
            nomes = grupo["Jogador"].tolist()
            pontos = int(grupo.iloc[0]["pontos"])
            cor, cor_borda, altura = specs[i]
            blocos[i] = _coluna_podio(i + 1, nomes, pontos, cor, cor_borda, altura)

        ordem = [b for b in [blocos[1], blocos[0], blocos[2]] if b is not None]
        podio_tbl = Table([ordem], colWidths=[5.4 * cm] * len(ordem))
        podio_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(podio_tbl)
        story.append(Spacer(1, 28))

    # TABELA COMPLETA COM TODAS AS COLUNAS
    df_show = df.reset_index().rename(columns={
        "pontos": "Pontos", "vitorias": "Vitórias", "derrotas": "Derrotas",
        "jogos": "Jogos", "saldo": "Saldo", "melhor_rodada": "Melhor Rodada", "folgas": "Folgas",
    })
    colunas = ["Pos", "Jogador", "Pontos", "Vitórias", "Derrotas", "Jogos", "Saldo", "Melhor Rodada", "Folgas"]
    dados = [colunas] + [[str(row[c]) for c in colunas] for _, row in df_show.iterrows()]

    tabela = Table(dados, colWidths=[1.2 * cm, 3.4 * cm, 1.6 * cm, 1.7 * cm, 1.7 * cm,
                                       1.3 * cm, 1.3 * cm, 2.5 * cm, 1.4 * cm],
                    repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela)

    # PÁGINA 2 (PAISAGEM) — HISTÓRICO DE PONTOS POR RODADA, POR JOGADOR
    historico_matriz, n_rodadas = montar_matriz_pontos_por_rodada()
    if n_rodadas > 0:
        story.append(NextPageTemplate("Paisagem"))
        story.append(PageBreak())
        story.append(Paragraph("Histórico de Pontos por Rodada", styles["Heading2"]))
        story.append(Spacer(1, 10))

        header = ["Jogador"] + [f"R{i+1}" for i in range(n_rodadas)] + ["Total", "Vit.", "Der."]
        dados2 = [header]
        for linha in historico_matriz:
            vals = [linha["jogador"]]
            for p in linha["pontos_por_rodada"]:
                vals.append(str(p) if p is not None else "-")
            vals += [str(linha["total"]), str(linha["vitorias"]), str(linha["derrotas"])]
            dados2.append(vals)

        largura_disp = largura_pais - 2 * margem_pais
        col_jogador = 3.2 * cm
        col_extra = 1.6 * cm
        largura_rodadas = largura_disp - col_jogador - 3 * col_extra
        col_rodada = max(largura_rodadas / n_rodadas, 0.9 * cm)
        col_widths = [col_jogador] + [col_rodada] * n_rodadas + [col_extra] * 3
        fonte = 8 if n_rodadas <= 12 else 6.5

        tabela2 = Table(dados2, colWidths=col_widths, repeatRows=1)
        tabela2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), fonte),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tabela2)

    doc.build(story)
    buffer.seek(0)
    return buffer


# ============================================================
# BACKUP
# ============================================================
def exportar_backup():
    data = {
        "players": shared["players"],
        "schedule": shared["schedule"],
        "rounds": shared["rounds"],
        "tournament_date": shared["tournament_date"].isoformat(),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def importar_backup(file):
    data = json.loads(file.read().decode("utf-8"))
    shared["players"] = data.get("players", [])
    shared["schedule"] = data.get("schedule")
    shared["rounds"] = data.get("rounds", [])
    if data.get("tournament_date"):
        shared["tournament_date"] = date.fromisoformat(data["tournament_date"])


# ============================================================
# SIDEBAR - MODO ORGANIZADOR
# ============================================================
with st.sidebar:
    st.header("🔐 Modo organizador")
    if not st.session_state.is_organizer:
        pin = st.text_input("PIN", type="password")
        if st.button("Entrar"):
            if pin == ORGANIZER_PIN:
                st.session_state.is_organizer = True
                st.rerun()
            else:
                st.error("PIN incorreto.")
    else:
        st.success("Modo organizador ativo")
        if st.button("Sair do modo organizador"):
            st.session_state.is_organizer = False
            st.rerun()

        st.divider()
        st.subheader("⚠️ Reiniciar torneio")
        st.caption("Apaga rodadas e calendário, mantém os jogadores cadastrados.")
        if st.checkbox("Confirmo que quero reiniciar"):
            if st.button("🔄 Reiniciar torneio"):
                shared["schedule"] = None
                shared["rounds"] = []
                st.rerun()

    st.divider()
    st.subheader("💾 Backup")
    st.download_button(
        "Baixar backup (JSON)",
        data=exportar_backup(),
        file_name=f"super12_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
    )
    if st.session_state.is_organizer:
        up = st.file_uploader("Carregar backup", type=["json"])
        if up is not None:
            importar_backup(up)
            st.success("Backup carregado!")
            st.rerun()

# ============================================================
# TÍTULO
# ============================================================
st.title("🎾 Super Arena Polese")

if not st.session_state.is_organizer:
    # Atualiza a tela sozinha a cada 15s para quem só está acompanhando,
    # sem precisar recarregar a página manualmente.
    st_autorefresh(interval=15_000, key="viewer_autorefresh")
    st.caption("🔴 Ao vivo — atualiza automaticamente a cada 15s")

if st.session_state.is_organizer:
    aba_jog, aba_rodada, aba_placar, aba_hist, aba_class = st.tabs(
        ["Jogadores", "Gerar Rodada", "Registrar Placar", "Histórico", "Classificação"]
    )
else:
    aba_hist, aba_class = st.tabs(["Histórico", "Classificação"])

# ============================================================
# ABA JOGADORES (só organizador)
# ============================================================
if st.session_state.is_organizer:
    with aba_jog:
        st.subheader("Jogadores")
        torneio_iniciado = len(shared["rounds"]) > 0

        if torneio_iniciado:
            st.info("🔒 Lista travada — o torneio já começou (para não quebrar o calendário "
                    "de rodadas). Use 'Reiniciar torneio' na barra lateral para editar.")
            for p in shared["players"]:
                st.write(f"• {p}")
        else:
            novo = st.text_input("Nome do jogador", key="novo_jogador")
            if st.button("Adicionar jogador"):
                nome = novo.strip()
                if nome and nome not in shared["players"]:
                    shared["players"].append(nome)
                    st.rerun()

            if shared["players"]:
                for p in shared["players"]:
                    c1, c2 = st.columns([4, 1])
                    c1.write(p)
                    if c2.button("Remover", key=f"rm_{p}"):
                        shared["players"].remove(p)
                        st.rerun()
                st.caption(f"Total: {len(shared["players"])} jogador(es). "
                           f"Ideal: múltiplo de 4 (ex: 8, 12, 16).")
            else:
                st.info("Nenhum jogador cadastrado ainda.")

# ============================================================
# ABA GERAR RODADA (só organizador)
# ============================================================
if st.session_state.is_organizer:
    with aba_rodada:
        st.subheader("Gerar rodada")
        n = len(shared["players"])

        if n < 4:
            st.warning("Cadastre pelo menos 4 jogadores para gerar rodadas.")
        else:
            # O calendário só é fixado no clique do botão (com a lista de
            # jogadores daquele momento). Antes disso, mostramos apenas uma
            # prévia do total de rodadas, que pode mudar se você ainda
            # estiver adicionando/removendo jogadores.
            if shared["schedule"] is not None:
                total_rodadas = len(shared["schedule"])
            else:
                total_rodadas = (n - 1) if n % 2 == 0 else n

            rodadas_geradas = len(shared["rounds"])
            torneio_completo = shared["schedule"] is not None and rodadas_geradas >= total_rodadas

            if torneio_completo:
                st.success("🏁 Torneio completo! Todo mundo já jogou com todo mundo. "
                           "Confira a Classificação final.")
            else:
                st.progress(rodadas_geradas / total_rodadas if total_rodadas else 0)
                st.caption(f"Rodada {rodadas_geradas + 1} de {total_rodadas}")
                if shared["schedule"] is None:
                    st.caption(f"({n} jogadores cadastrados — o calendário será fixado ao sortear a 1ª rodada)")
                if st.button("🔀 Sortear próxima rodada"):
                    if shared["schedule"] is None:
                        shared["schedule"] = gerar_calendario_completo(shared["players"])
                    pares = shared["schedule"][rodadas_geradas]
                    partidas, folgantes = montar_partidas_e_folgas(shared["players"], pares)
                    shared["rounds"].append({"partidas": partidas, "folgantes": folgantes})
                    st.rerun()

        if shared["rounds"]:
            st.divider()
            idx = len(shared["rounds"]) - 1
            ultima = shared["rounds"][idx]
            st.markdown(f"**Última rodada gerada: Rodada {idx + 1}**")
            for m in ultima["partidas"]:
                st.write(f"Quadra {m['quadra']}: {' / '.join(m['time1'])}  🆚  {' / '.join(m['time2'])}")
            if ultima["folgantes"]:
                st.caption(f"De folga: {', '.join(ultima['folgantes'])}")

# ============================================================
# ABA REGISTRAR PLACAR (só organizador)
# ============================================================
if st.session_state.is_organizer:
    with aba_placar:
        st.subheader("Registrar placar")
        if not shared["rounds"]:
            st.info("Gere uma rodada primeiro na aba 'Gerar Rodada'.")
        else:
            opcoes = [f"Rodada {i+1}" for i in range(len(shared["rounds"]))]
            escolha = st.selectbox("Selecione a rodada", opcoes, index=len(opcoes) - 1)
            idx = opcoes.index(escolha)
            partidas = shared["rounds"][idx]["partidas"]

            for j, m in enumerate(partidas):
                st.markdown(f"**Quadra {m['quadra']}**")
                c1, c2, c3 = st.columns([2, 1, 2])
                with c1:
                    st.write(" / ".join(m["time1"]))
                    p1 = st.number_input(
                        "Pontos", min_value=0, max_value=99,
                        value=m["placar1"] if m["placar1"] is not None else 0,
                        key=f"p1_{idx}_{j}"
                    )
                with c2:
                    st.write("×")
                with c3:
                    st.write(" / ".join(m["time2"]))
                    p2 = st.number_input(
                        "Pontos", min_value=0, max_value=99,
                        value=m["placar2"] if m["placar2"] is not None else 0,
                        key=f"p2_{idx}_{j}"
                    )
                shared["rounds"][idx]["partidas"][j]["placar1"] = p1
                shared["rounds"][idx]["partidas"][j]["placar2"] = p2
                st.divider()

            if st.button("💾 Salvar placares desta rodada"):
                st.success("Placares salvos!")

# ============================================================
# ABA HISTÓRICO (todo mundo vê)
# ============================================================
with aba_hist:
    st.subheader("Histórico de rodadas")
    if not shared["rounds"]:
        st.info("Nenhuma rodada gerada ainda.")
    else:
        df_hist = montar_tabela_historico()
        st.dataframe(df_hist, width='stretch', hide_index=True)

# ============================================================
# ABA CLASSIFICAÇÃO (todo mundo vê)
# ============================================================
with aba_class:
    st.subheader("Classificação geral")

    if st.session_state.is_organizer:
        shared["tournament_date"] = st.date_input(
            "Data do torneio", value=shared["tournament_date"]
        )
    else:
        st.caption(f"Data do torneio: {shared["tournament_date"].strftime('%d/%m/%Y')}")

    if not shared["players"]:
        st.info("Nenhum jogador cadastrado ainda.")
    else:
        df = calcular_classificacao()
        st.dataframe(
            df.rename(columns={
                "pontos": "Pontos", "vitorias": "Vitórias", "derrotas": "Derrotas",
                "jogos": "Jogos", "saldo": "Saldo", "melhor_rodada": "Melhor Rodada", "folgas": "Folgas"
            }),
            width='stretch',
            hide_index=True,
        )
        if shared["schedule"] is not None:
            st.caption(f"Rodadas jogadas: {len(shared["rounds"])} de {len(shared["schedule"])}")

        data_str = shared["tournament_date"].strftime("%d/%m/%Y")
        pdf_buffer = gerar_pdf_classificacao(df, data_str)
        st.download_button(
            "📄 Baixar classificação em PDF",
            data=pdf_buffer,
            file_name=f"classificacao_super12_{shared["tournament_date"].strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
        )
