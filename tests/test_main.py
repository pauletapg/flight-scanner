from datetime import date

import pytest

from scanner import historico, main, notificar, pesquisa
from scanner.pesquisa import Voo


def config():
    rota = {
        "nome": "Rio → Recife", "origem": "RIO", "destino": "REC",
        "ida_entre": [date(2030, 1, 1), date(2030, 1, 3)], "passo_dias": 1, "duracoes_dias": [7],
        "adultos": 1, "criancas": 0, "bebes_colo": 0, "classe": "economy",
        "filtros": {"preco_max": 3000}, "alerta": {"queda_percentual": 10},
    }
    # 3 combinações e 2 buscas por execução: o cursor do rodízio precisa avançar (ou não, no teste).
    geral = {"moeda": "BRL", "pausa_entre_buscas_seg": [0, 0], "max_buscas_por_execucao": 2, "resumo_diario_hora": 99}
    return {"geral": geral, "rotas": [rota]}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco temporário, Google falso (um voo de R$ 2.000 por combinação) e notificação gravada numa lista."""
    banco = tmp_path / "precos.db"
    enviados = []
    monkeypatch.setattr(main, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(pesquisa, "buscar", lambda origem, destino, ida, volta, **_: [
        Voo(origem, destino, ida, volta, 2000, "Gol", 0, 165, f"{ida} 13:50", f"{ida} 16:35", "https://exemplo")
    ])
    monkeypatch.setattr(notificar, "enviar", lambda texto, botoes=None: enviados.append(texto))
    return banco, enviados


def contar(banco, sql):
    con = historico.abrir(banco)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_dry_run_nao_grava_precos_nem_avanca_o_rodizio(ambiente, capsys):
    banco, enviados = ambiente
    main.executar(config(), dry_run=True)
    assert "Flight Scanner: 2 alerta(s)" in capsys.readouterr().out
    assert enviados == []
    # Se o teste gravasse, o preço dele viraria o mínimo do histórico e esconderia o alerta de queda seguinte.
    assert contar(banco, "SELECT COUNT(*) FROM precos") == 0
    assert contar(banco, "SELECT COUNT(*) FROM alertas") == 0
    assert contar(banco, "SELECT COUNT(*) FROM estado WHERE chave LIKE 'cursor:%'") == 0


def test_execucao_normal_grava_precos_alerta_e_rodizio(ambiente):
    banco, enviados = ambiente
    main.executar(config())
    assert len(enviados) == 1
    assert contar(banco, "SELECT COUNT(*) FROM precos") == 2
    assert contar(banco, "SELECT COUNT(*) FROM alertas") == 2
    assert contar(banco, "SELECT COUNT(*) FROM estado WHERE chave LIKE 'cursor:%'") == 1
