"""A CLI (scanner.buscar) continua com a mesma saída depois de passar a usar scanner.rotas e scanner.busca_avulsa."""

import sys
from datetime import date, timedelta

import pytest

from scanner import buscar, busca_avulsa, pesquisa, rotas
from tests.test_busca_avulsa import voo
from tests.test_rotas import CONFIG


@pytest.fixture
def config(tmp_path, monkeypatch):
    caminho = tmp_path / "config.yaml"
    caminho.write_text("geral:\n  moeda: BRL\n  pausa_entre_buscas_seg: [0, 0]\n\n" + CONFIG.split("\n\n", 1)[1],
                       encoding="utf-8")
    monkeypatch.setattr(rotas, "CAMINHO_CONFIG", caminho)
    monkeypatch.setattr(buscar, "CAMINHO_CONFIG", caminho)
    return caminho


def rodar(monkeypatch, *argumentos):
    monkeypatch.setattr(sys, "argv", ["buscar", *argumentos])
    buscar.main()


def test_listar(config, monkeypatch, capsys):
    rodar(monkeypatch, "--listar")
    saida = capsys.readouterr().out
    assert "[ativa] A: RIO → REC, 1 adulto(s), 0 criança(s), teto 5000" in saida
    assert "[PAUSADA] C: GIG → FOR" in saida
    assert "2 de 3 vagas ativas usadas." in saida


def test_pausar_retomar_e_aviso_de_excesso(config, monkeypatch, capsys):
    rodar(monkeypatch, "--pausar", "A")
    assert "Pausada (não gasta buscas): A" in capsys.readouterr().out
    rodar(monkeypatch, "--retomar", "A")
    rodar(monkeypatch, "--retomar", "C")
    rotas.adicionar({"nome": "D", "origem": "X", "destino": "Y", "pausada": True}, caminho=config)
    rodar(monkeypatch, "--retomar", "D")
    saida = capsys.readouterr().out
    assert "Retomada: C" in saida
    assert "Atenção: agora há mais de 3 buscas ativas" in saida


def test_rota_inexistente_lista_as_salvas(config, monkeypatch):
    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch, "--remover", "Z")
    assert str(erro.value) == "Não achei a busca 'Z'. As salvas são:\n  - A\n  - B\n  - C"


def test_salvar_com_nome_repetido(config, monkeypatch):
    with pytest.raises(SystemExit) as erro:
        buscar.salvar_no_config({"nome": "A", "origem": "X", "destino": "Y"})
    assert "Escolha outro --nome." in str(erro.value)


def test_salvar_sem_vaga_e_sem_terminal(config, monkeypatch):
    rotas.retomar("C", caminho=config)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(SystemExit) as erro:
        buscar.salvar_no_config({"nome": "D", "origem": "X", "destino": "Y"})
    assert "Sem terminal para perguntar" in str(erro.value)


def test_salvar_substituindo(config, monkeypatch, capsys):
    rotas.retomar("C", caminho=config)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    respostas = iter(["s", "2"])
    monkeypatch.setattr("builtins.input", lambda pergunta: next(respostas))
    buscar.salvar_no_config({"nome": "D", "origem": "X", "destino": "Y"})
    assert "Substituindo 'B'." in capsys.readouterr().out
    assert [r["nome"] for r in rotas.listar(config)] == ["A", "C", "D"]


def test_busca_mostra_progresso_e_resultados(config, monkeypatch, capsys):
    ida = date.today() + timedelta(days=60)
    monkeypatch.setattr(busca_avulsa.time, "sleep", lambda s: None)
    monkeypatch.setattr(pesquisa, "buscar", lambda o, d, i, v, **kw: [voo(i, 1855)])
    rodar(monkeypatch, "--origem", "RIO", "--destino", "REC", "--datas", ida.isoformat(), "--duracoes", "7",
          "--adultos", "2", "--criancas", "1")
    saida = capsys.readouterr().out
    assert "RIO → REC: 1 combinação(ões) de datas, 2 adulto(s), 1 criança(s), 0 bebê(s)" in saida
    assert f"[1/1] {ida:%d/%m} → {ida + timedelta(days=7):%d/%m}: 1 voo(s), melhor R$ 1.855" in saida
    assert "R$ 1.855 · " in saida and "(7 dias) · direto · ida 2h45 · sai 13:50 · Gol" in saida
    assert "https://exemplo" in saida


def test_busca_com_reservas_sem_chave(config, monkeypatch, capsys):
    ida = date.today() + timedelta(days=60)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(buscar, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(pesquisa, "buscar", lambda o, d, i, v, **kw: [voo(i, 1855)])
    rodar(monkeypatch, "--origem", "RIO", "--destino", "REC", "--datas", ida.isoformat(), "--reservas", "1")
    assert "melhor R$ 1.855\n\n--reservas precisa da SERPAPI_KEY no arquivo .env.\n" in capsys.readouterr().out
