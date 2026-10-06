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


def dados(con: sqlite3.Connection) -> list[dict]:
    """Os números do relatório, por rota: buscas, combinações de datas e, por hora e por dia da semana,
    quantas buscas, o desvio médio em % do preço da combinação e (por hora) quantos mínimos históricos.
    `por_hora` e `por_dia` ficam vazios enquanto nenhuma combinação tiver pelo menos 2 buscas."""
    # Menor preço de cada busca (uma busca = uma rota + datas num momento).
    linhas = con.execute(
        "SELECT rota, ida, volta, buscado_em, MIN(preco) FROM precos GROUP BY rota, ida, volta, buscado_em"
    ).fetchall()
    por_rota = defaultdict(lambda: defaultdict(list))
    for rota, ida, volta, buscado_em, preco in linhas:
        por_rota[rota][(ida, volta)].append((datetime.fromisoformat(buscado_em), preco))

    resultado = []
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
        resultado.append({
            "rota": rota,
            "buscas": sum(len(b) for b in combinacoes.values()),
            "combinacoes": len(combinacoes),
            "por_hora": [
                {"hora": h, "buscas": len(por_hora[h]), "desvio": mean(por_hora[h]), "minimos": minimos_por_hora[h]}
                for h in sorted(por_hora)
            ],
            "por_dia": [
                {"dia": d, "nome": DIAS[d], "buscas": len(por_dia[d]), "desvio": mean(por_dia[d])}
                for d in sorted(por_dia)
            ],
        })
    return resultado


def gerar(con: sqlite3.Connection) -> str:
    rotas = dados(con)
    if not rotas:
        return "Ainda não há buscas no histórico."
    saida = []
    for r in rotas:
        saida.append(f"=== {r['rota']} — {r['buscas']} buscas, {r['combinacoes']} combinações de datas ===")
        if not r["por_hora"]:
            saida.append("Poucos dados ainda: cada combinação de datas precisa de pelo menos 2 buscas.\n")
            continue

        saida.append("Hora   Buscas   Preço vs média   Mínimos históricos")
        for h in r["por_hora"]:
            saida.append(f"{h['hora']:02d}h   {h['buscas']:6d}   {h['desvio']:+13.1f}%   {h['minimos']:18d}")
        saida.append("")
        saida.append("Dia    Buscas   Preço vs média")
        for d in r["por_dia"]:
            saida.append(f"{d['nome']:5s}  {d['buscas']:6d}   {d['desvio']:+13.1f}%")
        saida.append("")
    return "\n".join(saida)


if __name__ == "__main__":
    from scanner.main import CAMINHO_BANCO
    from scanner import historico

    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    print(gerar(historico.abrir(CAMINHO_BANCO)))
