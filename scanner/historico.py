"""Histórico de preços e alertas em SQLite, e a decisão de quando alertar."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scanner.pesquisa import Voo

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS precos (
    buscado_em TEXT, rota TEXT, origem TEXT, destino TEXT, ida TEXT, volta TEXT,
    preco INTEGER, moeda TEXT, companhias TEXT, escalas INTEGER, duracao_min INTEGER,
    partida TEXT, chegada TEXT, passa_filtros INTEGER
);
CREATE INDEX IF NOT EXISTS precos_combinacao ON precos (rota, ida, volta);
CREATE TABLE IF NOT EXISTS alertas (
    enviado_em TEXT, rota TEXT, ida TEXT, volta TEXT, companhias TEXT, preco INTEGER
);
CREATE TABLE IF NOT EXISTS estado (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS reservas (
    consultado_em TEXT, rota TEXT, ida TEXT, volta TEXT, partida TEXT, preco_lista INTEGER,
    preco_reserva INTEGER, onde TEXT
);
"""


def abrir(caminho: Path | str) -> sqlite3.Connection:
    if caminho != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.executescript(_ESQUEMA)
    return con


def proximo_lote(con: sqlite3.Connection, chave: str, itens: list, n: int, avancar: bool = True) -> list:
    """Devolve os próximos n itens a partir do cursor salvo e avança o cursor (se `avancar`),
    dando a volta no fim da lista. Assim, execuções seguidas cobrem a lista toda."""
    if len(itens) <= n:
        return list(itens)
    linha = con.execute("SELECT valor FROM estado WHERE chave = ?", (chave,)).fetchone()
    inicio = int(linha[0]) % len(itens) if linha else 0
    lote = [itens[(inicio + i) % len(itens)] for i in range(n)]
    if not avancar:
        return lote
    con.execute(
        "INSERT OR REPLACE INTO estado (chave, valor) VALUES (?, ?)",
        (chave, str((inicio + n) % len(itens))),
    )
    con.commit()
    return lote


def _combinacao(rota: str, voo: Voo) -> tuple:
    return (rota, voo.ida.isoformat(), voo.volta.isoformat() if voo.volta else None)


SILENCIO_REPETICAO = timedelta(hours=12)


def deve_alertar(
    con: sqlite3.Connection, rota: str, voo: Voo, queda_percentual: float, agora: datetime | None = None
) -> tuple[str, int | None] | None:
    """Decide se o voo (que já passou nos filtros) merece alerta, olhando só o histórico anterior.

    - ("novo", None): nunca houve alerta para esta rota + datas.
    - ("queda", minimo): o preço caiu pelo menos queda_percentual abaixo do mínimo já visto.
    - None: nada de novo, ou o mesmo preço (ou maior) já foi avisado nas últimas 12 h.
    """
    combinacao = _combinacao(rota, voo)
    desde = ((agora or datetime.now()) - SILENCIO_REPETICAO).isoformat(timespec="seconds")
    repetido = con.execute(
        "SELECT 1 FROM alertas WHERE rota = ? AND ida = ? AND volta IS ? AND enviado_em >= ? AND preco <= ?",
        (*combinacao, desde, voo.preco),
    ).fetchone()
    if repetido:
        return None
    ja_alertado = con.execute(
        "SELECT 1 FROM alertas WHERE rota = ? AND ida = ? AND volta IS ?", combinacao
    ).fetchone()
    if not ja_alertado:
        return ("novo", None)

    (minimo,) = con.execute(
        "SELECT MIN(preco) FROM precos WHERE rota = ? AND ida = ? AND volta IS ? AND passa_filtros = 1",
        combinacao,
    ).fetchone()
    if minimo and voo.preco <= minimo * (1 - queda_percentual / 100):
        return ("queda", minimo)
    return None


def salvar(con: sqlite3.Connection, rota: str, voos: list[tuple[Voo, bool]], moeda: str, quando: datetime) -> None:
    """Guarda todos os voos de uma busca, marcando quais passaram nos filtros."""
    linhas = []
    for v, passou in voos:
        _, ida, volta = _combinacao(rota, v)
        linhas.append((
            quando.isoformat(timespec="seconds"), rota, v.origem, v.destino, ida, volta,
            v.preco, moeda, v.companhias, v.escalas, v.duracao_min, v.partida, v.chegada, int(passou),
        ))
    con.executemany("INSERT INTO precos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)
    con.commit()


def registrar_alerta(con: sqlite3.Connection, rota: str, voo: Voo, quando: datetime) -> None:
    _, ida, volta = _combinacao(rota, voo)
    con.execute(
        "INSERT INTO alertas VALUES (?, ?, ?, ?, ?, ?)",
        (quando.isoformat(timespec="seconds"), rota, ida, volta, voo.companhias, voo.preco),
    )
    con.commit()


def reserva_em_cache(con: sqlite3.Connection, rota: str, voo: Voo) -> tuple[int | None, str] | None:
    """Preço de reserva já consultado para este voo, se o preço da lista não mudou desde então.
    (None, "") significa que já consultamos e não havia opção com preço."""
    _, ida, volta = _combinacao(rota, voo)
    linha = con.execute(
        "SELECT preco_reserva, onde FROM reservas WHERE rota = ? AND ida = ? AND volta IS ? AND partida = ? "
        "AND preco_lista = ? ORDER BY consultado_em DESC LIMIT 1",
        (rota, ida, volta, voo.partida, voo.preco),
    ).fetchone()
    return linha


def salvar_reserva(con: sqlite3.Connection, rota: str, voo: Voo, resultado: tuple[int, str] | None, quando: datetime) -> None:
    _, ida, volta = _combinacao(rota, voo)
    preco, onde = resultado or (None, "")
    con.execute(
        "INSERT INTO reservas VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (quando.isoformat(timespec="seconds"), rota, ida, volta, voo.partida, voo.preco, preco, onde),
    )
    con.commit()


def serpapi_usadas(con: sqlite3.Connection, quando: datetime, no_dia: bool = False) -> int:
    """Consultas da SerpApi gastas no mês de `quando` (ou só no dia, com no_dia=True)."""
    chave = f"serpapi:{quando:%Y-%m-%d}" if no_dia else f"serpapi:{quando:%Y-%m}"
    linha = con.execute("SELECT valor FROM estado WHERE chave = ?", (chave,)).fetchone()
    return int(linha[0]) if linha else 0


def serpapi_somar(con: sqlite3.Connection, quando: datetime, n: int) -> None:
    if not n:
        return
    for no_dia, chave in ((False, f"serpapi:{quando:%Y-%m}"), (True, f"serpapi:{quando:%Y-%m-%d}")):
        con.execute(
            "INSERT OR REPLACE INTO estado (chave, valor) VALUES (?, ?)",
            (chave, str(serpapi_usadas(con, quando, no_dia) + n)),
        )
    con.commit()


def resumo_pendente(con: sqlite3.Connection, agora: datetime) -> bool:
    """Falta o aviso do dia: nenhum alerta nem resumo foi enviado hoje."""
    inicio = agora.strftime("%Y-%m-%dT00:00:00")
    if con.execute("SELECT 1 FROM alertas WHERE enviado_em >= ?", (inicio,)).fetchone():
        return False
    return con.execute("SELECT 1 FROM estado WHERE chave = ?", (f"resumo:{agora:%Y-%m-%d}",)).fetchone() is None


def marcar_resumo(con: sqlite3.Connection, agora: datetime) -> None:
    con.execute("INSERT OR REPLACE INTO estado (chave, valor) VALUES (?, '1')", (f"resumo:{agora:%Y-%m-%d}",))
    con.commit()


def melhor_recente(
    con: sqlite3.Connection, rota: str, filtros: dict, agora: datetime, horas: int = 24
) -> tuple | None:
    """(preco, ida, volta, companhias, escalas, duracao_min) do voo mais barato visto nas últimas
    `horas` que respeita as escalas e a duração dos filtros, sem olhar o preço (ele pode estar acima do teto)."""
    desde = (agora - timedelta(hours=horas)).isoformat(timespec="seconds")
    linhas = con.execute(
        "SELECT preco, ida, volta, companhias, escalas, duracao_min FROM precos "
        "WHERE rota = ? AND buscado_em >= ? ORDER BY preco",
        (rota, desde),
    )
    escalas_max, duracao_max = filtros.get("escalas_max"), filtros.get("duracao_max_horas")
    for linha in linhas:
        if escalas_max is not None and linha[4] > escalas_max:
            continue
        if duracao_max is not None and linha[5] > duracao_max * 60:
            continue
        return linha
    return None
