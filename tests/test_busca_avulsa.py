from datetime import date, timedelta

import pytest

from scanner import busca_avulsa, pesquisa
from scanner.pesquisa import Voo

IDA = date.today() + timedelta(days=60)


def voo(ida, preco, escalas=0, duracao_min=165):
    volta = ida + timedelta(days=7)
    return Voo("RIO", "REC", ida, volta, preco, "Gol", escalas, duracao_min,
               f"{ida} 13:50", f"{ida} 16:35", "https://exemplo")


def rota(**filtros):
    return {"nome": "Teste", "origem": "RIO", "destino": "REC",
            "ida_entre": [IDA, IDA + timedelta(days=1)], "passo_dias": 1, "duracoes_dias": [7],
            "adultos": 2, "criancas": 1, "bebes_colo": 0, "classe": "economy", "filtros": filtros}


GERAL = {"moeda": "BRL", "pausa_entre_buscas_seg": [0, 0]}


@pytest.fixture
def sem_pausa(monkeypatch):
    monkeypatch.setattr(busca_avulsa.time, "sleep", lambda s: None)


def test_combinacoes_da_rota():
    assert busca_avulsa.combinacoes_da_rota(rota()) == [
        (IDA, IDA + timedelta(days=7)), (IDA + timedelta(days=1), IDA + timedelta(days=8))]


def test_buscar_pega_o_melhor_de_cada_combinacao_e_avisa_o_progresso(monkeypatch, sem_pausa):
    pedidos = []

    def falso(origem, destino, ida, volta, **kw):
        pedidos.append((ida, kw))
        return [voo(ida, 3000), voo(ida, 2000 if ida == IDA else 1500), voo(ida, 1000, escalas=2)]

    monkeypatch.setattr(pesquisa, "buscar", falso)
    linhas = []
    voos = busca_avulsa.buscar(rota(escalas_max=1), GERAL, progresso=lambda i, n, t: linhas.append((i, n, t)))
    assert [v.preco for v in voos] == [1500, 2000]
    assert [(i, n) for i, n, _ in linhas] == [(1, 2), (2, 2)]
    assert "2 voo(s), melhor R$ 2.000" in linhas[0][2]
    assert pedidos[0][1]["adultos"] == 2 and pedidos[0][1]["escalas_max"] == 1


def test_buscar_aplica_o_preco_max_no_fim(monkeypatch, sem_pausa):
    monkeypatch.setattr(pesquisa, "buscar", lambda o, d, ida, volta, **kw: [voo(ida, 1800 if ida == IDA else 2500)])
    voos = busca_avulsa.buscar(rota(preco_max=2000), GERAL)
    assert [v.preco for v in voos] == [1800]


def test_buscar_continua_quando_uma_combinacao_falha(monkeypatch, sem_pausa):
    def falso(o, d, ida, volta, **kw):
        if ida == IDA:
            raise RuntimeError("bloqueado")
        return []

    monkeypatch.setattr(pesquisa, "buscar", falso)
    linhas = []
    assert busca_avulsa.buscar(rota(), GERAL, progresso=lambda i, n, t: linhas.append(t)) == []
    assert "falhou (bloqueado)" in linhas[0]
    assert "nenhum nos filtros" in linhas[1]


def test_reservas_sem_chave_avisa_sem_numero(monkeypatch, sem_pausa):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(pesquisa, "buscar", lambda o, d, ida, volta, **kw: [voo(ida, 1000)])
    linhas = []
    busca_avulsa.buscar(rota(), GERAL, reservas=1, progresso=lambda i, n, t: linhas.append((i, n, t)))
    assert linhas[-1][:2] == (None, None)
    assert "SERPAPI_KEY" in linhas[-1][2]
