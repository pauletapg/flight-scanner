from datetime import date, datetime

import pytest

from scanner import historico, main, pesquisa
from scanner.filtros import passa
from scanner.pesquisa import Voo

ROTA = "Rio → Recife"


def voo(preco=1855, reserva=None):
    v = Voo("RIO", "REC", date(2026, 12, 20), date(2026, 12, 27), preco, "Gol", 0, 165,
            "2026-12-20 13:50", "2026-12-20 16:35", "https://exemplo")
    v.reserva_preco, v.reserva_onde = reserva, ("Zupper" if reserva else "")
    return v


@pytest.fixture
def con():
    return historico.abrir(":memory:")


def test_filtro_de_preco_usa_o_menor_entre_lista_e_reserva():
    assert not passa(voo(1950), {"preco_max": 1900})
    assert passa(voo(1950, reserva=1700), {"preco_max": 1900})
    assert passa(voo(1950), {"preco_max": 1900}, ignorar_preco=True)


def test_cache_vale_so_enquanto_o_preco_da_lista_nao_muda(con):
    historico.salvar_reserva(con, ROTA, voo(1855), (1667, "Zupper"), datetime(2026, 10, 3, 10))
    assert historico.reserva_em_cache(con, ROTA, voo(1855)) == (1667, "Zupper")
    assert historico.reserva_em_cache(con, ROTA, voo(1914)) is None


def test_saldo_serpapi_divide_o_mes_pelos_dias(con, monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "x")

    class Agora(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 10, 3, 12)  # faltam 29 dias em outubro

    monkeypatch.setattr(main, "datetime", Agora)
    geral = {"serpapi": {"limite_mensal": 240}}
    assert main.saldo_serpapi(con, geral) == 8
    historico.serpapi_somar(con, datetime(2026, 10, 3, 9), 6)
    assert main.saldo_serpapi(con, geral) == 2
    historico.serpapi_somar(con, datetime(2026, 10, 3, 11), 3)
    assert main.saldo_serpapi(con, geral) == 0
    monkeypatch.delenv("SERPAPI_KEY")
    assert main.saldo_serpapi(con, geral) == 0


def test_opcoes_reserva_segue_ida_volta_e_reserva(monkeypatch):
    def opcao(hora, preco, escalas=0, **tokens):
        return {"price": preco, "flights": [{"departure_airport": {"time": f"2026-12-20 {hora}"}}] * (escalas + 1), **tokens}

    respostas = {
        "ida": {"best_flights": [opcao("11:10", 2101, departure_token="errado"),
                                 opcao("13:50", 1855, departure_token="d1")]},
        "d1": {"best_flights": [opcao("14:35", 1855, booking_token="b1"), opcao("18:00", 2000, booking_token="b2")]},
        "b1": {"booking_options": [
            {"together": {"book_with": "Gol", "price": 1855}},
            {"together": {"book_with": "Zupper", "price": 1667}},
            {"together": {"book_with": "Sem preço"}},
            {"separate_tickets": True, "departing": {"book_with": "A", "price": 900},
             "returning": {"book_with": "B", "price": 800}},
        ]},
    }
    pedidos = []

    def falso(params):
        pedidos.append(params)
        return respostas[params.get("booking_token") or params.get("departure_token") or "ida"]

    monkeypatch.setattr(pesquisa, "_serpapi", falso)
    assert pesquisa.opcoes_reserva(voo()) == (1667, "Zupper")
    assert len(pedidos) == 3
    assert pedidos[0]["departure_id"] == "/m/06gmr"
    assert pedidos[0]["return_date"] == "2026-12-27"


def test_alerta_mostra_preco_da_agencia():
    texto = main.formatar_alerta([(ROTA, voo(1855, reserva=1667), ("novo", None))], "BRL")
    assert "R$ 1.855" in texto
    assert "R$ 1.667 em" in texto
