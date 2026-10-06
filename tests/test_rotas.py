import shutil

import pytest
import yaml

from scanner import rotas
from scanner.main import PASTA

CONFIG = """geral:
  moeda: BRL   # comentário do geral

# Comentário antes das rotas.
rotas:

  - nome: A
    origem: RIO
    destino: REC
    adultos: 1   # comentário dentro da rota A
    filtros: {preco_max: 5000}

  - nome: B
    origem: GRU
    destino: SSA
    adultos: 2

  - nome: C
    pausada: true
    origem: GIG
    destino: FOR
    adultos: 1
"""


def nova(nome="Nova"):
    return {"nome": nome, "origem": "SDU", "destino": "CGH", "adultos": 1, "criancas": 0,
            "filtros": {"preco_max": 900}, "alerta": {"queda_percentual": 10}}


@pytest.fixture
def config(tmp_path):
    caminho = tmp_path / "config.yaml"
    caminho.write_text(CONFIG, encoding="utf-8")
    return caminho


def nomes(caminho):
    return [r["nome"] for r in rotas.listar(caminho)]


def test_listar_devolve_as_rotas_com_o_estado(config):
    lista = rotas.listar(config)
    assert [r["nome"] for r in lista] == ["A", "B", "C"]
    assert lista[2]["pausada"] is True


def test_listar_config_sem_rotas(tmp_path):
    caminho = tmp_path / "config.yaml"
    caminho.write_text("geral:\n  moeda: BRL\nrotas:\n", encoding="utf-8")
    assert rotas.listar(caminho) == []


def test_adicionar_acrescenta_no_fim_e_preserva_comentarios(config):
    rotas.adicionar(nova(), caminho=config)
    texto = config.read_text(encoding="utf-8")
    assert nomes(config) == ["A", "B", "C", "Nova"]
    assert "# comentário do geral" in texto
    assert "# Comentário antes das rotas." in texto
    assert "# comentário dentro da rota A" in texto
    assert rotas.listar(config)[3]["filtros"] == {"preco_max": 900}


def test_adicionar_nome_repetido(config):
    with pytest.raises(rotas.NomeRepetido):
        rotas.adicionar(nova("B"), caminho=config)
    assert config.read_text(encoding="utf-8") == CONFIG


def test_adicionar_com_vagas_esgotadas_lista_as_ativas(config):
    rotas.retomar("C", caminho=config)
    antes = config.read_text(encoding="utf-8")
    with pytest.raises(rotas.VagasEsgotadas) as erro:
        rotas.adicionar(nova(), caminho=config)
    assert erro.value.ativas == ["A", "B", "C"]
    assert config.read_text(encoding="utf-8") == antes


def test_adicionar_substituindo_uma_ativa(config):
    rotas.retomar("C", caminho=config)
    rotas.adicionar(nova(), substituir="B", caminho=config)
    assert nomes(config) == ["A", "C", "Nova"]


def test_adicionar_substituindo_rota_inexistente(config):
    with pytest.raises(rotas.RotaNaoEncontrada):
        rotas.adicionar(nova(), substituir="Z", caminho=config)


def test_pausar_e_retomar(config):
    rotas.pausar("A", caminho=config)
    assert rotas.listar(config)[0]["pausada"] is True
    assert "# comentário dentro da rota A" in config.read_text(encoding="utf-8")
    rotas.retomar("A", caminho=config)
    assert config.read_text(encoding="utf-8") == CONFIG


def test_retomar_devolve_quantas_ativas_ficaram(config):
    assert rotas.retomar("C", caminho=config) == 3


def test_remover(config):
    rotas.remover("B", caminho=config)
    assert nomes(config) == ["A", "C"]
    assert "# comentário dentro da rota A" in config.read_text(encoding="utf-8")


@pytest.mark.parametrize("acao", [rotas.pausar, rotas.retomar, rotas.remover])
def test_acao_em_rota_inexistente(config, acao):
    with pytest.raises(rotas.RotaNaoEncontrada) as erro:
        acao("Z", caminho=config)
    assert erro.value.nomes == ["A", "B", "C"]


def test_editar_substitui_a_rota_no_mesmo_lugar(config):
    rotas.editar("B", nova("B2"), caminho=config)
    assert nomes(config) == ["A", "B2", "C"]
    assert rotas.listar(config)[1]["destino"] == "CGH"
    assert "# comentário dentro da rota A" in config.read_text(encoding="utf-8")


def test_editar_mantem_o_estado_pausado(config):
    rotas.editar("C", nova("C"), caminho=config)
    assert rotas.listar(config)[2]["pausada"] is True
    rotas.editar("A", nova("A") | {"pausada": True}, caminho=config)
    assert not rotas.listar(config)[0].get("pausada")


def test_editar_para_nome_de_outra_rota(config):
    with pytest.raises(rotas.NomeRepetido):
        rotas.editar("A", nova("B"), caminho=config)
    with pytest.raises(rotas.RotaNaoEncontrada):
        rotas.editar("Z", nova("Z"), caminho=config)


def test_comentario_logo_abaixo_de_rotas_sobrevive(tmp_path):
    caminho = tmp_path / "config.yaml"
    caminho.write_text(CONFIG.replace("rotas:\n\n", "rotas:\n  # rotas de dezembro\n\n"), encoding="utf-8")
    original = caminho.read_text(encoding="utf-8")
    rotas.pausar("A", caminho=caminho)
    rotas.retomar("A", caminho=caminho)
    assert caminho.read_text(encoding="utf-8") == original
    rotas.remover("A", caminho=caminho)
    assert "  # rotas de dezembro\n\n  - nome: B" in caminho.read_text(encoding="utf-8")


def test_ativas(config):
    assert [r["nome"] for r in rotas.ativas(rotas.listar(config))] == ["A", "B"]


def test_montar_rota_no_formato_do_config():
    rota = rotas.montar_rota(" sdu ", "cgh", nome="  ", ida_entre=["2026-12-20", "2026-12-23"], passo_dias=2,
                             duracoes_dias=[7], adultos=2, filtros={"preco_max": 900, "escalas_max": None},
                             queda_percentual=15)
    assert rota == {
        "nome": "SDU → CGH", "origem": "SDU", "destino": "CGH", "ida_entre": ["2026-12-20", "2026-12-23"],
        "passo_dias": 2, "duracoes_dias": [7], "adultos": 2, "criancas": 0, "bebes_colo": 0, "classe": "economy",
        "filtros": {"preco_max": 900}, "alerta": {"queda_percentual": 15},
    }
    assert list(rota) == list(rotas.montar_rota("SDU", "CGH", ida_entre=["x", "y"], duracoes_dias=[7]))  # mesma ordem
    so_datas = rotas.montar_rota("SDU", "CGH", nome="Natal", datas=["2026-12-20", ("2026-12-21", "2026-12-28")])
    assert so_datas["nome"] == "Natal" and so_datas["datas"] == ["2026-12-20", ["2026-12-21", "2026-12-28"]]
    assert "ida_entre" not in so_datas and "duracoes_dias" not in so_datas


def test_gravacao_atomica_nao_deixa_temporario(config):
    rotas.adicionar(nova(), caminho=config)
    assert [p.name for p in config.parent.iterdir()] == ["config.yaml"]


def test_preserva_fim_de_linha_crlf(tmp_path):
    caminho = tmp_path / "config.yaml"
    caminho.write_bytes(CONFIG.replace("\n", "\r\n").encode("utf-8"))
    rotas.adicionar(nova(), caminho=caminho)
    dados = caminho.read_bytes()
    assert dados.count(b"\n") == dados.count(b"\r\n")


def test_config_real_ida_e_volta_byte_a_byte(tmp_path):
    caminho = tmp_path / "config.yaml"
    shutil.copyfile(PASTA / "config.yaml", caminho)
    original = caminho.read_bytes()
    lista = rotas.listar(caminho)
    assert lista, "o config.yaml real deveria ter ao menos uma rota"
    primeira = lista[0]["nome"]

    rotas.pausar(primeira, caminho=caminho)
    rotas.retomar(primeira, caminho=caminho)
    assert caminho.read_bytes() == original

    if len([r for r in lista if not r.get("pausada")]) < rotas.MAX_ROTAS:
        rotas.adicionar(nova("Teste temporário"), caminho=caminho)
        rotas.remover("Teste temporário", caminho=caminho)
        assert caminho.read_bytes() == original
    assert yaml.safe_load(caminho.read_text(encoding="utf-8"))["geral"]
