from datetime import date, datetime

import pytest

from scanner import historico, relatorio
from scanner.main import formatar_alerta
from scanner.pesquisa import Voo

ROTA = "São Paulo → Lisboa"


def voo(preco, ida=date(2026, 11, 10), volta=date(2026, 11, 20)):
    return Voo("GRU", "LIS", ida, volta, preco, "TAP", 0, 595, "2026-11-10 01:30", "2026-11-10 14:25", "https://exemplo")


@pytest.fixture
def con():
    return historico.abrir(":memory:")


def test_primeiro_voo_nos_filtros_gera_alerta(con):
    assert historico.deve_alertar(con, ROTA, voo(4000), 10) == ("novo", None)


def test_depois_do_alerta_so_alerta_com_queda_suficiente(con):
    v = voo(4000)
    historico.salvar(con, ROTA, [(v, True)], "BRL", datetime(2026, 10, 3, 1))
    historico.registrar_alerta(con, ROTA, v, datetime(2026, 10, 3, 1))

    assert historico.deve_alertar(con, ROTA, voo(4000), 10) is None  # mesmo preço: não repete
    assert historico.deve_alertar(con, ROTA, voo(3700), 10) is None  # caiu só 7,5%
    assert historico.deve_alertar(con, ROTA, voo(3600), 10) == ("queda", 4000)


def test_nao_repete_mesmo_preco_em_12h(con):
    v = voo(4000)
    historico.registrar_alerta(con, ROTA, v, datetime(2026, 10, 3, 1))
    historico.registrar_alerta(con, ROTA, voo(3000), datetime(2026, 10, 3, 1))
    agora = datetime(2026, 10, 3, 12)
    assert historico.deve_alertar(con, ROTA, voo(3000), 10, agora) is None
    assert historico.deve_alertar(con, ROTA, voo(3500), 10, agora) is None  # maior que o já avisado


def test_minimo_ignora_voos_fora_dos_filtros(con):
    v = voo(4000)
    historico.salvar(con, ROTA, [(v, True), (voo(2000), False)], "BRL", datetime(2026, 10, 3, 1))
    historico.registrar_alerta(con, ROTA, v, datetime(2026, 10, 3, 1))
    assert historico.deve_alertar(con, ROTA, voo(3500), 10) == ("queda", 4000)


def test_alerta_e_por_combinacao_de_datas(con):
    v = voo(4000)
    historico.registrar_alerta(con, ROTA, v, datetime(2026, 10, 3, 1))
    assert historico.deve_alertar(con, ROTA, voo(4000, volta=date(2026, 11, 24)), 10) == ("novo", None)
    assert historico.deve_alertar(con, ROTA, voo(4000, volta=None), 10) == ("novo", None)


def test_proximo_lote_roda_pela_lista_toda(con):
    itens = list(range(7))
    assert historico.proximo_lote(con, "c", itens, 3) == [0, 1, 2]
    assert historico.proximo_lote(con, "c", itens, 3) == [3, 4, 5]
    assert historico.proximo_lote(con, "c", itens, 3) == [6, 0, 1]
    assert historico.proximo_lote(con, "outra", itens, 3) == [0, 1, 2]
    assert historico.proximo_lote(con, "c", [1, 2], 3) == [1, 2]


def test_relatorio_compara_cada_busca_com_a_media_da_combinacao(con):
    # Mesma combinação buscada às 01h (mais barato) e às 13h (mais caro), em dois dias.
    for dia, hora, preco in [(3, 1, 3600), (3, 13, 4400), (4, 1, 3600), (4, 13, 4400)]:
        historico.salvar(con, ROTA, [(voo(preco), True)], "BRL", datetime(2026, 10, dia, hora))
    texto = relatorio.gerar(con)
    assert "4 buscas, 1 combinações" in texto
    assert "01h        2           -10.0%" in texto
    assert "13h        2           +10.0%" in texto


def test_relatorio_sem_dados(con):
    assert relatorio.gerar(con) == "Ainda não há buscas no histórico."


def test_mensagem_do_alerta():
    alertas = [(ROTA, voo(3600), ("queda", 4000)), (ROTA, voo(4100, volta=None), ("novo", None))]
    texto = formatar_alerta(alertas, "BRL")
    assert "2 alerta(s)" in texto
    assert "R$ 3.600 · direto · 9h55 · TAP" in texto
    assert "Caiu 10% (mínimo anterior R$ 4.000)" in texto
    assert "10/11 (só ida)" in texto
    assert texto.index("R$ 3.600") < texto.index("R$ 4.100")  # mais barato primeiro


def test_resumo_diario_e_melhor_recente():
    from datetime import datetime
    from scanner.pesquisa import Voo

    con = historico.abrir(":memory:")
    agora = datetime(2026, 10, 6, 9, 5)
    caro = Voo("RIO", "REC", date(2026, 12, 20), date(2026, 12, 27), 6576, "Azul", 0, 165, "", "", "x")
    longo = Voo("RIO", "REC", date(2026, 12, 21), date(2026, 12, 28), 3000, "X", 2, 165, "", "", "")
    historico.salvar(con, "Rota", [(caro, False), (longo, False)], "BRL", datetime(2026, 10, 6, 1, 0))
    melhor = historico.melhor_recente(con, "Rota", {"escalas_max": 1}, agora)
    assert melhor[0] == 6576  # ignora o de 2 escalas
    assert historico.melhor_recente(con, "Rota", {}, datetime(2026, 10, 8)) is None  # fora das 24 h

    assert historico.resumo_pendente(con, agora)
    historico.marcar_resumo(con, agora)
    assert not historico.resumo_pendente(con, agora)
    assert historico.resumo_pendente(con, datetime(2026, 10, 7, 9))
