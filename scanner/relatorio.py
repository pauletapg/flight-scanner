"""Relatório: em que hora do dia e dia da semana as buscas encontraram preços mais baixos.

Cada combinação de datas (ida/volta) tem o seu próprio nível de preço, então cada busca é
comparada com a média da sua combinação. Um valor negativo quer dizer que, naquela hora,
os preços encontrados estavam abaixo da média.
"""

import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def gerar(con: sqlite3.Connection) -> str:
    # Menor preço de cada busca (uma busca = uma rota + datas num momento).
    linhas = con.execute(
        "SELECT rota, ida, volta, buscado_em, MIN(preco) FROM precos GROUP BY rota, ida, volta, buscado_em"
    ).fetchall()
    if not linhas:
        return "Ainda não há buscas no histórico."

    por_rota = defaultdict(lambda: defaultdict(list))
    for rota, ida, volta, buscado_em, preco in linhas:
        por_rota[rota][(ida, volta)].append((datetime.fromisoformat(buscado_em), preco))

    saida = []
    for rota, combinacoes in por_rota.items():
        por_hora, por_dia, minimos_por_hora = defaultdict(list), defaultdict(list), Counter()
        for buscas in combinacoes.values():
            if len(buscas) < 2:
                continue
            media = mean(p for _, p in buscas)
            for quando, preco in buscas:
                desvio = (preco / media - 1) * 100
                por_hora[quando.hour].append(desvio)
                por_dia[quando.weekday()].append(desvio)
            minimos_por_hora[min(buscas, key=lambda b: b[1])[0].hour] += 1

        total = sum(len(b) for b in combinacoes.values())
        saida.append(f"=== {rota} — {total} buscas, {len(combinacoes)} combinações de datas ===")
        if not por_hora:
            saida.append("Poucos dados ainda: cada combinação de datas precisa de pelo menos 2 buscas.\n")
            continue

        saida.append("Hora   Buscas   Preço vs média   Mínimos históricos")
        for hora in sorted(por_hora):
            saida.append(
                f"{hora:02d}h   {len(por_hora[hora]):6d}   {mean(por_hora[hora]):+13.1f}%   {minimos_por_hora[hora]:18d}"
            )
        saida.append("")
        saida.append("Dia    Buscas   Preço vs média")
        for dia in sorted(por_dia):
            saida.append(f"{DIAS[dia]:5s}  {len(por_dia[dia]):6d}   {mean(por_dia[dia]):+13.1f}%")
        saida.append("")
    return "\n".join(saida)


if __name__ == "__main__":
    from scanner.main import CAMINHO_BANCO
    from scanner import historico

    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    print(gerar(historico.abrir(CAMINHO_BANCO)))
