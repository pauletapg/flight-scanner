from datetime import date

import primp
import pytest
import requests

from scanner import pesquisa
from scanner.pesquisa import Voo

IDA, VOLTA = date(2030, 1, 1), date(2030, 1, 8)


def voo():
    return Voo("RIO", "REC", IDA, VOLTA, 2000, "Gol", 0, 165, "2030-01-01 13:50", "2030-01-01 16:35", "https://exemplo")


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(pesquisa.time, "sleep", lambda s: None)
    monkeypatch.setenv("SERPAPI_KEY", "chave-secreta-123")


def test_pagina_sem_dados_tenta_o_google_de_novo_antes_da_serpapi(monkeypatch):
    respostas = [pesquisa.PaginaSemDados("sem lista"), [voo()]]

    def google(*args):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(pesquisa, "_buscar_google", google)
    monkeypatch.setattr(pesquisa, "_buscar_serpapi", lambda *a: pytest.fail("não devia gastar a SerpApi"))
    assert pesquisa.buscar("RIO", "REC", IDA, VOLTA) == [voo()]


def test_google_falha_duas_vezes_usa_a_serpapi(monkeypatch):
    def google(*args):
        raise pesquisa.PaginaSemDados("sem lista")

    monkeypatch.setattr(pesquisa, "_buscar_google", google)
    monkeypatch.setattr(pesquisa, "_buscar_serpapi", lambda *a: [voo()])
    assert pesquisa.buscar("RIO", "REC", IDA, VOLTA) == [voo()]


def test_sem_internet_nao_tenta_a_serpapi(monkeypatch):
    def google(*args):
        raise primp.DNSError("https://www.google.com/... > error resolving DNS")

    monkeypatch.setattr(pesquisa, "_buscar_google", google)
    monkeypatch.setattr(pesquisa, "tem_internet", lambda host="": False)
    monkeypatch.setattr(pesquisa, "_buscar_serpapi", lambda *a: pytest.fail("não devia tentar a SerpApi"))
    with pytest.raises(pesquisa.SemConexao):
        pesquisa.buscar("RIO", "REC", IDA, VOLTA)


def test_erro_de_rede_com_internet_tenta_de_novo(monkeypatch):
    respostas = [primp.ConnectError("x > conexão recusada"), [voo()]]

    def google(*args):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(pesquisa, "_buscar_google", google)
    monkeypatch.setattr(pesquisa, "tem_internet", lambda host="": True)
    assert pesquisa.buscar("RIO", "REC", IDA, VOLTA) == [voo()]


def test_falha_da_serpapi_nao_expoe_a_chave_nem_conta_no_plano(monkeypatch):
    def get(url, params, timeout):
        raise requests.ConnectionError(f"Max retries exceeded with url: /search.json?api_key={params['api_key']}")

    monkeypatch.setattr(pesquisa.requests, "get", get)
    monkeypatch.setattr(pesquisa, "tem_internet", lambda host="": True)
    antes = pesquisa.serpapi_chamadas
    with pytest.raises(RuntimeError) as erro:
        pesquisa._serpapi({})
    assert "chave-secreta-123" not in str(erro.value)
    assert erro.value.__cause__ is None and erro.value.__suppress_context__
    assert pesquisa.serpapi_chamadas == antes

    monkeypatch.setattr(pesquisa, "tem_internet", lambda host="": False)
    with pytest.raises(pesquisa.SemConexao):
        pesquisa._serpapi({})


def test_pagina_sem_script_de_dados_vira_erro_claro():
    with pytest.raises(pesquisa.PaginaSemDados):
        pesquisa._todos_os_voos("<html><body>Antes de continuar</body></html>")


def test_esperar_internet_desiste_depois_do_limite(monkeypatch):
    monkeypatch.setattr(pesquisa, "tem_internet", lambda host="": False)
    relogio = iter(range(0, 1000, 15))
    monkeypatch.setattr(pesquisa.time, "monotonic", lambda: next(relogio))
    assert pesquisa.esperar_internet(max_seg=60, intervalo_seg=15) is False
