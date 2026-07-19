import streamlit as st
import pandas as pd
import random
import json
from datetime import datetime
from itertools import combinations

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
        "rounds": [],            # lista de rodadas -> cada rodada é lista de partidas
        "partner_count": {},     # {"NomeA|NomeB": n_vezes_juntos}
        "bye_count": {},         # {"Nome": n_vezes_de_folga}
        "is_organizer": False,
        "current_round_idx": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


def pair_key(a, b):
    return "|".join(sorted([a, b]))


# ============================================================
# LÓGICA DE SORTEIO DE RODADA
# ============================================================
def gerar_rodada(players, partner_count, bye_count, tentativas=400):
    n = len(players)
    resto = n % 4

    melhor = None
    melhor_penalidade = None

    for _ in range(tentativas):
        pool = players[:]
        random.shuffle(pool)

        # define quem fica de folga nessa rodada (os com menos folgas até agora)
        if resto:
            ordenado_por_folga = sorted(pool, key=lambda p: (bye_count.get(p, 0), random.random()))
            folgantes = ordenado_por_folga[:resto]
            jogam = [p for p in pool if p not in folgantes]
        else:
            folgantes = []
            jogam = pool

        random.shuffle(jogam)
        duplas = [tuple(sorted(jogam[i:i + 2])) for i in range(0, len(jogam), 2)]

        penalidade = sum(partner_count.get(pair_key(*d), 0) for d in duplas)

        if melhor_penalidade is None or penalidade < melhor_penalidade:
            melhor_penalidade = penalidade
            melhor = (duplas, folgantes)
        if melhor_penalidade == 0:
            break

    duplas, folgantes = melhor
    # monta as partidas: dupla[0] vs dupla[1], dupla[2] vs dupla[3]...
    partidas = []
    for i in range(0, len(duplas) - 1, 2):
        partidas.append({
            "quadra": i // 2 + 1,
            "time1": list(duplas[i]),
            "time2": list(duplas[i + 1]),
            "placar1": None,
            "placar2": None,
        })
    # se sobrar 1 dupla sem adversário (número ímpar de duplas), ela fica sem partida nessa rodada
    if len(duplas) % 2 == 1:
        sobra = duplas[-1]
        for p in sobra:
            if p not in folgantes:
                folgantes.append(p)

    return partidas, folgantes


def registrar_rodada_no_historico(partidas, folgantes):
    for m in partidas:
        for time in (m["time1"], m["time2"]):
            if len(time) == 2:
                k = pair_key(time[0], time[1])
                st.session_state.partner_count[k] = st.session_state.partner_count.get(k, 0) + 1
    for p in folgantes:
        st.session_state.bye_count[p] = st.session_state.bye_count.get(p, 0) + 1


# ============================================================
# CÁLCULO DE CLASSIFICAÇÃO
# ============================================================
def calcular_classificacao():
    stats = {p: {"pontos": 0, "vitorias": 0, "derrotas": 0, "jogos": 0, "saldo": 0, "folgas": 0}
              for p in st.session_state.players}

    for p, n in st.session_state.bye_count.items():
        if p in stats:
            stats[p]["folgas"] = n

    for rodada in st.session_state.rounds:
        for m in rodada:
            if m["placar1"] is None or m["placar2"] is None:
                continue
            s1, s2 = m["placar1"], m["placar2"]
            for p in m["time1"]:
                if p not in stats:
                    continue
                stats[p]["pontos"] += s1
                stats[p]["jogos"] += 1
                stats[p]["saldo"] += (s1 - s2)
                if s1 > s2:
                    stats[p]["vitorias"] += 1
                elif s1 < s2:
                    stats[p]["derrotas"] += 1
            for p in m["time2"]:
                if p not in stats:
                    continue
                stats[p]["pontos"] += s2
                stats[p]["jogos"] += 1
                stats[p]["saldo"] += (s2 - s1)
                if s2 > s1:
                    stats[p]["vitorias"] += 1
                elif s2 < s1:
                    stats[p]["derrotas"] += 1

    df = pd.DataFrame.from_dict(stats, orient="index")
    df.index.name = "Jogador"
    df = df.sort_values(by=["pontos", "vitorias", "saldo"], ascending=False)
    df.insert(0, "Pos", range(1, len(df) + 1))
    return df


# ============================================================
# BACKUP
# ============================================================
def exportar_backup():
    data = {
        "players": st.session_state.players,
        "rounds": st.session_state.rounds,
        "partner_count": st.session_state.partner_count,
        "bye_count": st.session_state.bye_count,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def importar_backup(file):
    data = json.loads(file.read().decode("utf-8"))
    st.session_state.players = data.get("players", [])
    st.session_state.rounds = data.get("rounds", [])
    st.session_state.partner_count = data.get("partner_count", {})
    st.session_state.bye_count = data.get("bye_count", {})


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
    aba_jog, aba_rodada, aba_placar, aba_class = st.tabs(
        ["Jogadores", "Gerar Rodada", "Registrar Placar", "Classificação"]
    )
else:
    (aba_class,) = st.tabs(["Classificação"])

# ============================================================
# ABA JOGADORES (só organizador)
# ============================================================
if st.session_state.is_organizer:
    with aba_jog:
        st.subheader("Jogadores")
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
        st.subheader("Gerar nova rodada")
        n = len(st.session_state.players)
        if n < 4:
            st.warning("Cadastre pelo menos 4 jogadores para gerar uma rodada.")
        else:
            if st.button("🔀 Sortear rodada"):
                partidas, folgantes = gerar_rodada(
                    st.session_state.players,
                    st.session_state.partner_count,
                    st.session_state.bye_count,
                )
                registrar_rodada_no_historico(partidas, folgantes)
                st.session_state.rounds.append(partidas)
                st.session_state["ultima_folga"] = folgantes
                st.rerun()

        if st.session_state.rounds:
            st.divider()
            idx = len(st.session_state.rounds) - 1
            st.markdown(f"**Última rodada gerada: Rodada {idx + 1}**")
            for m in st.session_state.rounds[idx]:
                st.write(f"Quadra {m['quadra']}: {' / '.join(m['time1'])}  🆚  {' / '.join(m['time2'])}")
            folgas = st.session_state.get("ultima_folga", [])
            if folgas:
                st.caption(f"De folga: {', '.join(folgas)}")

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
            partidas = st.session_state.rounds[idx]

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
                st.session_state.rounds[idx][j]["placar1"] = p1
                st.session_state.rounds[idx][j]["placar2"] = p2
                st.divider()

            if st.button("💾 Salvar placares desta rodada"):
                st.success("Placares salvos!")

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
        st.caption(f"Rodadas jogadas: {len(st.session_state.rounds)}")
