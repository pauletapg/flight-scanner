import sys
import threading
import time
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from scanner import busca_avulsa, historico, notificar, pesquisa, rotas
from scanner.pesquisa import Voo
from scanner.web import app as web

IDA = date.today() + timedelta(days=60)

CONFIG = """\
geral:
  moeda: BRL
  pausa_entre_buscas_seg: [0, 0]   # sem pausa nos testes
  serpapi:
    limite_mensal: 200

# Comentário que precisa sobreviver às edições.
rotas:

  - nome: A
    origem: RIO
    destino: REC
    datas: [2026-12-20]
    adultos: 1
    criancas: 0
    bebes_colo: 0
    classe: economy

  - nome: B
    pausada: true
    origem: GRU
    destino: LIS
    datas: [2026-12-20]
    adultos: 1
    criancas: 0
    bebes_colo: 0
    classe: economy
"""

LOG = """\
2026-10-05 19:45:28,000 INFO Início: 10 de 12 combinações de datas
2026-10-05 19:45:40,100 ERROR Falha na busca
2026-10-05 19:46:27,635 INFO Fim: nenhum alerta
"""


def nova_rota(nome, **extra):
    return {"nome": nome, "origem": "rio", "destino": "rec", "ida_entre": [str(IDA), str(IDA + timedelta(days=1))],
            "duracoes_dias": [7], "adultos": 2, "filtros": {"preco_max": 3000, "escalas_max": 1}, **extra}


def voo(ida, preco):
    return Voo("RIO", "REC", ida, ida + timedelta(days=7), preco, "Gol", 0, 165,
               f"{ida} 13:50", f"{ida} 16:35", "https://exemplo")


@pytest.fixture
def caminhos(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    log = tmp_path / "scanner.log"
    log.write_text(LOG, encoding="utf-8")
    return {"config": config, "banco": tmp_path / "precos.db", "log": log}


@pytest.fixture
def cliente(caminhos):
    app = web.criar_app(
        caminho_config=caminhos["config"], caminho_banco=caminhos["banco"], caminho_log=caminhos["log"],
        consultar_tarefas=lambda: [{"nome": "VooScanner", "proxima": "2026-10-05T21:01:10"}],
        comando_scanner=[sys.executable, "-c", "import sys; print('scanner rodou', sys.argv[1:])"],
    )
    return TestClient(app)


def esperar(cliente, url, campo="estado", timeout=10):
    fim = time.time() + timeout
    while time.time() < fim:
        dados = cliente.get(url).json()
        if dados and dados[campo] != "rodando":
            return dados
        time.sleep(0.05)
    raise AssertionError(f"{url} não terminou")


# --- rotas -----------------------------------------------------------------------------------------------

def test_listar_rotas(cliente):
    r = cliente.get("/api/rotas")
    assert r.status_code == 200
    dados = r.json()
    assert [(x["nome"], x["pausada"]) for x in dados["rotas"]] == [("A", False), ("B", True)]
    assert dados["rotas"][0]["datas"] == ["2026-12-20"]
    assert (dados["ativas"], dados["max_ativas"]) == (1, 3)


def test_adicionar_rota_grava_no_config_preservando_comentarios(cliente, caminhos):
    r = cliente.post("/api/rotas", json={"rota": nova_rota("Nova", alerta={"queda_percentual": 15})})
    assert r.status_code == 201, r.text
    salva = rotas.listar(caminhos["config"])[-1]
    assert salva["nome"] == "Nova" and salva["origem"] == "RIO" and salva["destino"] == "REC"
    assert salva["ida_entre"] == [IDA, IDA + timedelta(days=1)] and salva["passo_dias"] == 1
    assert salva["criancas"] == 0 and salva["classe"] == "economy"
    assert salva["filtros"] == {"preco_max": 3000, "escalas_max": 1}
    assert salva["alerta"] == {"queda_percentual": 15}
    assert "# Comentário que precisa sobreviver" in caminhos["config"].read_text(encoding="utf-8")


def test_nome_padrao_e_origem_destino(cliente, caminhos):
    rota = nova_rota(None)
    del rota["nome"]
    assert cliente.post("/api/rotas", json={"rota": rota}).status_code == 201
    assert rotas.listar(caminhos["config"])[-1]["nome"] == "RIO → REC"


def test_adicionar_sem_vaga_responde_409_e_aceita_substituir(cliente, caminhos):
    for nome in ("C", "D"):
        assert cliente.post("/api/rotas", json={"rota": nova_rota(nome)}).status_code == 201
    r = cliente.post("/api/rotas", json={"rota": nova_rota("E")})
    assert r.status_code == 409
    assert r.json()["detail"] == "Já há 3 buscas monitoradas (o máximo)."
    assert r.json()["ativas"] == ["A", "C", "D"]

    r = cliente.post("/api/rotas", json={"rota": nova_rota("E"), "substituir": "C"})
    assert r.status_code == 201
    assert [x["nome"] for x in rotas.listar(caminhos["config"])] == ["A", "B", "D", "E"]


def test_nome_repetido_responde_409(cliente):
    r = cliente.post("/api/rotas", json={"rota": nova_rota("A")})
    assert r.status_code == 409
    assert r.json()["detail"] == "Já existe uma rota chamada 'A' no config.yaml."


def test_rota_sem_datas_responde_422_em_portugues(cliente):
    rota = nova_rota("X")
    del rota["ida_entre"]
    r = cliente.post("/api/rotas", json={"rota": rota})
    assert r.status_code == 422
    assert "Informe as datas" in r.json()["detail"]


def test_dados_invalidos_respondem_422_em_portugues(cliente):
    r = cliente.post("/api/rotas", json={"rota": nova_rota("X", adultos=0)})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Dados inválidos em rota.adultos:")


def test_editar_rota_mantem_a_pausa(cliente, caminhos):
    r = cliente.put("/api/rotas", json={"nome": "B", "rota": nova_rota("B2")})
    assert r.status_code == 200, r.text
    editada = rotas.listar(caminhos["config"])[1]
    assert editada["nome"] == "B2" and editada["pausada"] is True and editada["origem"] == "RIO"


def test_editar_rota_inexistente_responde_404(cliente):
    r = cliente.put("/api/rotas", json={"nome": "Z", "rota": nova_rota("Z")})
    assert r.status_code == 404
    assert r.json()["detail"] == "Não achei a busca 'Z'."


def test_pausar_retomar_remover(cliente, caminhos):
    assert cliente.post("/api/rotas/acao", json={"nome": "A", "acao": "pausar"}).status_code == 200
    assert rotas.listar(caminhos["config"])[0]["pausada"] is True
    r = cliente.post("/api/rotas/acao", json={"nome": "B", "acao": "retomar"})
    assert r.status_code == 200 and r.json()["ativas"] == 1
    assert cliente.post("/api/rotas/acao", json={"nome": "A", "acao": "remover"}).status_code == 200
    assert [x["nome"] for x in rotas.listar(caminhos["config"])] == ["B"]


def test_retomar_com_3_ativas_responde_409(cliente, caminhos):
    for nome in ("C", "D"):
        cliente.post("/api/rotas", json={"rota": nova_rota(nome)})
    r = cliente.post("/api/rotas/acao", json={"nome": "B", "acao": "retomar"})
    assert r.status_code == 409
    assert r.json()["ativas"] == ["A", "C", "D"]
    assert rotas.listar(caminhos["config"])[1]["pausada"] is True


def test_acao_invalida_e_rota_inexistente(cliente):
    assert cliente.post("/api/rotas/acao", json={"nome": "A", "acao": "apagar"}).status_code == 422
    assert cliente.post("/api/rotas/acao", json={"nome": "Z", "acao": "pausar"}).status_code == 404


# --- busca avulsa ----------------------------------------------------------------------------------------

@pytest.fixture
def buscador(monkeypatch):
    """pesquisa.buscar falso: o preço depende da data; `liberar` segura a busca até o teste mandar."""
    liberar = threading.Event()
    liberar.set()

    def falso(origem, destino, ida, volta, **kw):
        liberar.wait(10)
        return [voo(ida, 2000 if ida == IDA else 1500), voo(ida, 4000)]

    monkeypatch.setattr(pesquisa, "buscar", falso)
    monkeypatch.setattr(busca_avulsa.time, "sleep", lambda s: None)
    return liberar


def test_busca_avulsa_com_progresso_e_resultados(cliente, buscador):
    r = cliente.post("/api/busca", json={"rota": nova_rota("X")})
    assert r.status_code == 202, r.text
    assert r.json()["n"] == 2
    dados = esperar(cliente, f"/api/busca/{r.json()['id']}")
    assert dados["estado"] == "concluida"
    assert (dados["i"], dados["n"]) == (2, 2)
    assert len(dados["linhas"]) == 2 and "melhor R$ 1.500" in dados["linhas"][1]["texto"]
    assert [v["preco"] for v in dados["resultados"]] == [1500, 2000]
    assert dados["resultados"][0]["link"] == "https://exemplo"
    assert dados["resultados"][0]["menor_preco"] == 1500
    assert dados["resultados"][0]["ida"] == str(IDA + timedelta(days=1))


def test_segunda_busca_ao_mesmo_tempo_responde_409(cliente, buscador):
    buscador.clear()
    primeira = cliente.post("/api/busca", json={"rota": nova_rota("X")}).json()["id"]
    r = cliente.post("/api/busca", json={"rota": nova_rota("Y")})
    assert r.status_code == 409
    assert "Já há uma busca em andamento" in r.json()["detail"]
    buscador.set()
    esperar(cliente, f"/api/busca/{primeira}")
    assert cliente.post("/api/busca", json={"rota": nova_rota("Y")}).status_code == 202


def test_busca_com_erro_fica_registrada(cliente, monkeypatch):
    def quebra(*a, **kw):
        raise KeyError("geral")

    monkeypatch.setattr(busca_avulsa, "buscar", quebra)
    id_ = cliente.post("/api/busca", json={"rota": nova_rota("X")}).json()["id"]
    dados = esperar(cliente, f"/api/busca/{id_}")
    assert dados["estado"] == "erro" and "geral" in dados["erro"]


def test_busca_grande_pede_forcar(cliente, buscador):
    rota = nova_rota("X", ida_entre=[str(IDA), str(IDA + timedelta(days=30))])  # 31 combinações
    r = cliente.post("/api/busca", json={"rota": rota})
    assert r.status_code == 422
    assert "São 31 buscas" in r.json()["detail"]
    assert cliente.post("/api/busca", json={"rota": rota, "forcar": True}).status_code == 202


def test_busca_sem_datas_no_futuro(cliente):
    rota = nova_rota("X", ida_entre=["2020-01-01", "2020-01-02"])
    r = cliente.post("/api/busca", json={"rota": rota})
    assert r.status_code == 422 and r.json()["detail"] == "Nenhuma data no futuro para buscar."


def test_busca_inexistente(cliente):
    assert cliente.get("/api/busca/nao-existe").status_code == 404


# --- histórico ------------------------------------------------------------------------------------------

@pytest.fixture
def com_historico(caminhos):
    con = historico.abrir(caminhos["banco"])
    ida = date(2026, 12, 20)
    historico.salvar(con, "A", [(voo(ida, 3000), True), (voo(ida, 2500), False)], "BRL", datetime(2026, 10, 5, 1))
    historico.salvar(con, "A", [(voo(ida, 2800), True)], "BRL", datetime(2026, 10, 5, 3))
    historico.salvar(con, "A", [(voo(ida, 2700), True)], "BRL", datetime(2026, 10, 6, 1))
    historico.salvar(con, "Outra", [(voo(ida, 900), True)], "BRL", datetime(2026, 10, 5, 1))
    historico.registrar_alerta(con, "A", voo(ida, 2800), datetime(2026, 10, 5, 3))
    con.close()


def test_historico_por_rota(cliente, com_historico):
    dados = cliente.get("/api/historico", params={"rota": "A"}).json()
    assert dados["rotas"] == ["A", "Outra"]
    assert dados["pontos"][0] == {"buscado_em": "2026-10-05T01:00:00", "ida": "2026-12-20", "volta": "2026-12-27",
                                  "menor_preco": 2500, "menor_nos_filtros": 3000}
    assert [p["menor_preco"] for p in dados["pontos"]] == [2500, 2800, 2700]


def test_historico_sem_rota_so_lista_as_rotas(cliente, com_historico):
    assert cliente.get("/api/historico").json() == {"rotas": ["A", "Outra"], "rota": None, "pontos": []}


def test_alertas(cliente, com_historico):
    alertas = cliente.get("/api/alertas").json()
    assert alertas == [{"enviado_em": "2026-10-05T03:00:00", "rota": "A", "ida": "2026-12-20",
                        "volta": "2026-12-27", "companhias": "Gol", "preco": 2800}]
    assert cliente.get("/api/alertas", params={"rota": "Outra"}).json() == []


def test_relatorio(cliente, com_historico):
    dados = cliente.get("/api/relatorio").json()
    assert dados["texto"].startswith("=== A — 3 buscas, 1 combinações de datas ===")
    assert [r["rota"] for r in dados["rotas"]] == ["A", "Outra"]
    assert [h["hora"] for h in dados["rotas"][0]["por_hora"]] == [1, 3]


# --- status e ações -------------------------------------------------------------------------------------

def test_status(cliente):
    dados = cliente.get("/api/status").json()
    assert dados["ultima_execucao"]["fim_texto"] == "Fim: nenhum alerta"
    assert dados["erros"][0]["mensagem"] == "Falha na busca"
    assert dados["serpapi"] == {"usadas_mes": 0, "usadas_hoje": 0, "limite_mensal": 200}
    assert dados["tarefas"][0]["nome"] == "VooScanner"
    assert dados["execucao"] is None


def test_rodar_agora_em_dry_run(cliente):
    r = cliente.post("/api/executar", json={"dry_run": True})
    assert r.status_code == 202, r.text
    dados = esperar(cliente, "/api/executar")
    assert dados["estado"] == "concluida" and dados["codigo"] == 0 and dados["dry_run"] is True
    assert "scanner rodou ['--dry-run']" in dados["saida"]
    assert cliente.get("/api/status").json()["execucao"]["codigo"] == 0


def test_rodar_agora_uma_por_vez(caminhos):
    app = web.criar_app(caminho_config=caminhos["config"], caminho_banco=caminhos["banco"],
                        caminho_log=caminhos["log"], consultar_tarefas=lambda: [],
                        comando_scanner=[sys.executable, "-c", "import time; time.sleep(1.5); print('ok')"])
    cliente = TestClient(app)
    assert cliente.post("/api/executar", json={}).status_code == 202
    r = cliente.post("/api/executar", json={"dry_run": True})
    assert r.status_code == 409 and "já está rodando" in r.json()["detail"]
    dados = esperar(cliente, "/api/executar")
    assert dados["dry_run"] is False and dados["saida"].strip() == "ok"


def test_rodar_agora_com_falha(caminhos):
    app = web.criar_app(caminho_config=caminhos["config"], caminho_banco=caminhos["banco"],
                        caminho_log=caminhos["log"], consultar_tarefas=lambda: [],
                        comando_scanner=[sys.executable, "-c", "raise SystemExit('Máximo de 3 rotas')"])
    cliente = TestClient(app)
    cliente.post("/api/executar", json={})
    dados = esperar(cliente, "/api/executar")
    assert dados["estado"] == "erro" and dados["codigo"] == 1 and "Máximo de 3 rotas" in dados["saida"]


def test_notificacao_de_teste(cliente, monkeypatch):
    enviadas = []
    monkeypatch.setattr(notificar, "enviar", lambda texto, botoes=None: enviadas.append((texto, botoes)))
    assert cliente.post("/api/notificacao-teste").status_code == 200
    assert enviadas[0][0].startswith("✈️ Flight Scanner: teste")


def test_notificacao_sem_credenciais(cliente, monkeypatch):
    def sem(texto, botoes=None):
        raise notificar.SemCredenciais("defina NTFY_TOPIC")

    monkeypatch.setattr(notificar, "enviar", sem)
    r = cliente.post("/api/notificacao-teste")
    assert r.status_code == 422 and "defina NTFY_TOPIC" in r.json()["detail"]


def test_notificacao_com_falha_no_envio(cliente, monkeypatch):
    def falha(texto, botoes=None):
        raise ConnectionError("sem internet")

    monkeypatch.setattr(notificar, "enviar", falha)
    r = cliente.post("/api/notificacao-teste")
    assert r.status_code == 502 and "sem internet" in r.json()["detail"]


# --- página -----------------------------------------------------------------------------------------------

def test_pagina_inicial(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Flight Scanner" in r.text
    for tela in ("#buscar", "#rotas", "#historico", "#status"):
        assert f'href="{tela}"' in r.text


def test_pagina_carrega_estilo_e_script(cliente):
    pagina = cliente.get("/").text
    for arquivo, tipo in (("estilo.css", "text/css"), ("app.js", "javascript")):
        assert f'"{arquivo}"' in pagina
        r = cliente.get(f"/{arquivo}")
        assert r.status_code == 200 and tipo in r.headers["content-type"]
