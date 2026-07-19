import streamlit as st
import pandas as pd
import random
import json
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================
st.set_page_config(page_title="Super 12 - Beach Tênis", page_icon="🎾", layout="centered")

# Troque esse PIN antes de compartilhar o link do app!
ORGANIZER_PIN = "1234"

# ============================================================
# ESTADO
# ============================================================
def init_state():
    defaults = {
        "players": [],           # lista de nomes
        "schedule": None,        # calendário completo: lista de rodadas -> lista de duplas [nome1, nome2]
        "rounds": [],            # rodadas já geradas: [{"partidas": [...], "folgantes": [...]}, ...]
        "is_organizer": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


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
    stats = {p: {"pontos": 0, "vitorias": 0, "derrotas": 0, "jogos": 0, "saldo": 0, "folgas": 0}
              for p in st.session_state.players}

    for rodada in st.session_state.rounds:
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
            for p in m["time2"]:
                if p not in stats:
                    continue
                stats[p]["pontos"] += s2
                stats[p]["jogos"] += 1
                stats[p]["saldo"] += (s2 - s1)
                stats[p]["vitorias"] += 1 if s2 > s1 else 0
                stats[p]["derrotas"] += 1 if s2 < s1 else 0

    df = pd.DataFrame.from_dict(stats, orient="index")
    df.index.name = "Jogador"
    df = df.sort_values(by=["pontos", "vitorias", "saldo"], ascending=False)
    df.insert(0, "Pos", range(1, len(df) + 1))
    return df


def montar_tabela_historico():
    linhas = []
    for i, rodada in enumerate(st.session_state.rounds, start=1):
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
# BACKUP
# ============================================================
def exportar_backup():
    data = {
        "players": st.session_state.players,
        "schedule": st.session_state.schedule,
        "rounds": st.session_state.rounds,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def importar_backup(file):
    data = json.loads(file.read().decode("utf-8"))
    st.session_state.players = data.get("players", [])
    st.session_state.schedule = data.get("schedule")
    st.session_state.rounds = data.get("rounds", [])


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
                st.session_state.schedule = None
                st.session_state.rounds = []
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
st.title("🎾 Super 12 - Beach Tênis")

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
        torneio_iniciado = len(st.session_state.rounds) > 0

        if torneio_iniciado:
            st.info("🔒 Lista travada — o torneio já começou (para não quebrar o calendário "
                    "de rodadas). Use 'Reiniciar torneio' na barra lateral para editar.")
            for p in st.session_state.players:
                st.write(f"• {p}")
        else:
            novo = st.text_input("Nome do jogador", key="novo_jogador")
            if st.button("Adicionar jogador"):
                nome = novo.strip()
                if nome and nome not in st.session_state.players:
                    st.session_state.players.append(nome)
                    st.rerun()

            if st.session_state.players:
                for p in st.session_state.players:
                    c1, c2 = st.columns([4, 1])
                    c1.write(p)
                    if c2.button("Remover", key=f"rm_{p}"):
                        st.session_state.players.remove(p)
                        st.rerun()
                st.caption(f"Total: {len(st.session_state.players)} jogador(es). "
                           f"Ideal: múltiplo de 4 (ex: 8, 12, 16).")
            else:
                st.info("Nenhum jogador cadastrado ainda.")

# ============================================================
# ABA GERAR RODADA (só organizador)
# ============================================================
if st.session_state.is_organizer:
    with aba_rodada:
        st.subheader("Gerar rodada")
        n = len(st.session_state.players)

        if n < 4:
            st.warning("Cadastre pelo menos 4 jogadores para gerar rodadas.")
        else:
            # O calendário só é fixado no clique do botão (com a lista de
            # jogadores daquele momento). Antes disso, mostramos apenas uma
            # prévia do total de rodadas, que pode mudar se você ainda
            # estiver adicionando/removendo jogadores.
            if st.session_state.schedule is not None:
                total_rodadas = len(st.session_state.schedule)
            else:
                total_rodadas = (n - 1) if n % 2 == 0 else n

            rodadas_geradas = len(st.session_state.rounds)
            torneio_completo = st.session_state.schedule is not None and rodadas_geradas >= total_rodadas

            if torneio_completo:
                st.success("🏁 Torneio completo! Todo mundo já jogou com todo mundo. "
                           "Confira a Classificação final.")
            else:
                st.progress(rodadas_geradas / total_rodadas if total_rodadas else 0)
                st.caption(f"Rodada {rodadas_geradas + 1} de {total_rodadas}")
                if st.session_state.schedule is None:
                    st.caption(f"({n} jogadores cadastrados — o calendário será fixado ao sortear a 1ª rodada)")
                if st.button("🔀 Sortear próxima rodada"):
                    if st.session_state.schedule is None:
                        st.session_state.schedule = gerar_calendario_completo(st.session_state.players)
                    pares = st.session_state.schedule[rodadas_geradas]
                    partidas, folgantes = montar_partidas_e_folgas(st.session_state.players, pares)
                    st.session_state.rounds.append({"partidas": partidas, "folgantes": folgantes})
                    st.rerun()

        if st.session_state.rounds:
            st.divider()
            idx = len(st.session_state.rounds) - 1
            ultima = st.session_state.rounds[idx]
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
        if not st.session_state.rounds:
            st.info("Gere uma rodada primeiro na aba 'Gerar Rodada'.")
        else:
            opcoes = [f"Rodada {i+1}" for i in range(len(st.session_state.rounds))]
            escolha = st.selectbox("Selecione a rodada", opcoes, index=len(opcoes) - 1)
            idx = opcoes.index(escolha)
            partidas = st.session_state.rounds[idx]["partidas"]

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
                st.session_state.rounds[idx]["partidas"][j]["placar1"] = p1
                st.session_state.rounds[idx]["partidas"][j]["placar2"] = p2
                st.divider()

            if st.button("💾 Salvar placares desta rodada"):
                st.success("Placares salvos!")

# ============================================================
# ABA HISTÓRICO (todo mundo vê)
# ============================================================
with aba_hist:
    st.subheader("Histórico de rodadas")
    if not st.session_state.rounds:
        st.info("Nenhuma rodada gerada ainda.")
    else:
        df_hist = montar_tabela_historico()
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

# ============================================================
# ABA CLASSIFICAÇÃO (todo mundo vê)
# ============================================================
with aba_class:
    st.subheader("Classificação geral")
    if not st.session_state.players:
        st.info("Nenhum jogador cadastrado ainda.")
    else:
        df = calcular_classificacao()
        st.dataframe(
            df.rename(columns={
                "pontos": "Pontos", "vitorias": "Vitórias", "derrotas": "Derrotas",
                "jogos": "Jogos", "saldo": "Saldo", "folgas": "Folgas"
            }),
            use_container_width=True,
            hide_index=True,
        )
        if st.session_state.schedule is not None:
            st.caption(f"Rodadas jogadas: {len(st.session_state.rounds)} de {len(st.session_state.schedule)}")
