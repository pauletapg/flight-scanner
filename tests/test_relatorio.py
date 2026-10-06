from datetime import date, datetime

import pytest

from scanner import historico, relatorio
from scanner.pesquisa import Voo


def voo(preco, ida=date(2026, 11, 10)):
    return Voo("GRU", "LIS", ida, date(2026, 11, 20), preco, "TAP", 0, 595, "x", "y", "https://exemplo")


@pytest.fixture
def con():
    con = historico.abrir(":memory:")
    # Rota A: uma combinação buscada 4 vezes (01h mais barato, 13h mais caro) e outra só 1 vez; rota B: 1 busca.
    for dia, hora, preco in [(3, 1, 3600), (3, 13, 4400), (4, 1, 3700), (5, 13, 4300)]:
        historico.salvar(con, "A", [(voo(preco), True), (voo(preco + 500), False)], "BRL", datetime(2026, 10, dia, hora))
    historico.salvar(con, "A", [(voo(5000, ida=date(2026, 11, 11)), True)], "BRL", datetime(2026, 10, 3, 1))
    historico.salvar(con, "B", [(voo(5000), True)], "BRL", datetime(2026, 10, 3, 1))
    return con


def test_texto_do_relatorio_nao_mudou(con):
    assert relatorio.gerar(con) == (
        "=== A — 5 buscas, 2 combinações de datas ===\n"
        "Hora   Buscas   Preço vs média   Mínimos históricos\n"
        "01h        2            -8.7%                    1\n"
        "13h        2            +8.8%                    0\n"
        "\n"
        "Dia    Buscas   Preço vs média\n"
        "seg         1            +7.5%\n"
        "sáb         2            +0.0%\n"
        "dom         1            -7.5%\n"
        "\n"
        "=== B — 1 buscas, 1 combinações de datas ===\n"
        "Poucos dados ainda: cada combinação de datas precisa de pelo menos 2 buscas.\n"
    )


def test_dados_por_hora_e_por_dia(con):
    a, b = relatorio.dados(con)
    assert (a["rota"], a["buscas"], a["combinacoes"]) == ("A", 5, 2)
    assert [(h["hora"], h["buscas"], round(h["desvio"], 1), h["minimos"]) for h in a["por_hora"]] == [
        (1, 2, -8.7, 1), (13, 2, 8.8, 0)]
    assert [(d["dia"], d["nome"], d["buscas"], round(d["desvio"], 1)) for d in a["por_dia"]] == [
        (0, "seg", 1, 7.5), (5, "sáb", 2, 0.0), (6, "dom", 1, -7.5)]
    assert (b["rota"], b["buscas"], b["por_hora"], b["por_dia"]) == ("B", 1, [], [])


def test_dados_sem_historico():
    assert relatorio.dados(historico.abrir(":memory:")) == []
