from datetime import datetime

from scanner import historico
from scanner.web import status

LOG = """\
2026-10-05 17:45:28,372 INFO Início: 10 de 12 combinações de datas
2026-10-05 17:46:27,635 WARNING Notificação não configurada (defina NTFY_TOPIC). Alerta não enviado:
✈️ Flight Scanner: 1 alerta(s)
2026-10-05 17:46:27,700 INFO Fim: nenhum alerta
2026-10-05 19:45:28,000 INFO Início: 10 de 12 combinações de datas
2026-10-05 19:45:40,100 ERROR Falha na busca Rio → Recife 2026-12-21 → 2026-12-29
Traceback (most recent call last):
RuntimeError: bloqueado
2026-10-05 19:46:27,635 INFO Fim: 1 alerta(s) enviado(s)
"""

# Saída real do schtasks (Windows em português): uma linha por gatilho; outras tarefas no meio.
CABECALHO = ('"Nome do host","Nome da tarefa","Hora da próxima execução","Status","Modo de Logon",'
             '"Horário da última execução","Último resultado","Autor","Tarefa a ser executada","Iniciar em",'
             '"Comentário","Estado de tarefa agendada"')


def linha(nome, proxima, ultima="05/10/2026 19:45:24", resultado="0", estado="Habilitado"):
    return (f'"PC","{nome}","{proxima}","Pronto","Interativo","{ultima}","{resultado}","PC\\paulo",'
            f'"pythonw.exe -m scanner.main","D:\\voo","Busca voos","{estado}"')


SCHTASKS = "\n".join([
    CABECALHO,
    linha("\\OutraTarefa", "05/10/2026 20:00:00"),
    linha("\\VooScanner", "05/10/2026 21:08:43"),
    linha("\\VooScanner", "05/10/2026 21:01:10"),
    linha("\\VooScanner", "06/10/2026 01:06:31"),
    CABECALHO,
    linha("\\Microsoft\\Windows\\FlightScannerFalsa", "N/A"),
])


def test_ler_fim_le_so_o_final_sem_linha_cortada(tmp_path):
    arquivo = tmp_path / "scanner.log"
    arquivo.write_text("".join(f"linha {i}\n" for i in range(1000)), encoding="utf-8")
    linhas = status.ler_fim(arquivo, max_bytes=100)
    assert linhas[-1] == "linha 999"
    assert all(l.startswith("linha ") and len(l) >= 9 for l in linhas)
    assert len(linhas) < 15


def test_ler_fim_sem_arquivo(tmp_path):
    assert status.ler_fim(tmp_path / "nao-existe.log") == []


def test_entradas_juntam_as_linhas_de_continuacao():
    entradas = status.entradas(LOG.splitlines())
    assert len(entradas) == 6
    assert entradas[1]["nivel"] == "WARNING"
    assert entradas[1]["quando"] == "2026-10-05T17:46:27"
    assert entradas[1]["mensagem"].endswith("Alerta não enviado:\n✈️ Flight Scanner: 1 alerta(s)")


def test_ultima_execucao_pega_o_ultimo_inicio_e_o_fim_dele():
    ultima = status.ultima_execucao(status.entradas(LOG.splitlines()))
    assert ultima == {
        "inicio": "2026-10-05T19:45:28", "inicio_texto": "Início: 10 de 12 combinações de datas",
        "fim": "2026-10-05T19:46:27", "fim_texto": "Fim: 1 alerta(s) enviado(s)",
    }


def test_ultima_execucao_em_andamento_ou_interrompida_fica_sem_fim():
    linhas = LOG.splitlines()[:-1]
    assert status.ultima_execucao(status.entradas(linhas))["fim"] is None
    assert status.ultima_execucao([]) is None


def test_erros_recentes_do_mais_novo_para_o_mais_antigo():
    erros = status.erros_recentes(status.entradas(LOG.splitlines()))
    assert [e["nivel"] for e in erros] == ["ERROR", "WARNING"]
    assert "RuntimeError: bloqueado" in erros[0]["mensagem"]
    assert len(status.erros_recentes(status.entradas(LOG.splitlines()), n=1)) == 1


def test_ler_schtasks_acha_flightscanner_e_voo_scanner():
    tarefas = status.ler_schtasks(SCHTASKS)
    assert tarefas == [{
        "nome": "VooScanner", "status": "Pronto", "situacao": "Habilitado",
        "proxima": "2026-10-05T21:01:10", "ultima": "2026-10-05T19:45:24", "ultimo_resultado": "0",
    }]
    renomeada = status.ler_schtasks(SCHTASKS.replace("\\VooScanner", "\\FlightScanner"))
    assert renomeada[0]["nome"] == "FlightScanner"


def test_ler_schtasks_sem_proxima_execucao():
    tarefas = status.ler_schtasks("\n".join([CABECALHO, linha("\\FlightScanner", "N/A", ultima="N/A", estado="Desabilitado")]))
    assert tarefas[0]["proxima"] is None and tarefas[0]["ultima"] is None
    assert tarefas[0]["situacao"] == "Desabilitado"


def test_obter_junta_log_cota_e_tarefa(tmp_path):
    log = tmp_path / "scanner.log"
    log.write_text(LOG, encoding="utf-8")
    banco = tmp_path / "precos.db"
    historico.serpapi_somar(historico.abrir(banco), datetime.now(), 7)
    geral = {"serpapi": {"limite_mensal": 240}}

    dados = status.obter(log, banco, geral, consultar_tarefas=lambda: status.ler_schtasks(SCHTASKS))
    assert dados["ultima_execucao"]["fim_texto"] == "Fim: 1 alerta(s) enviado(s)"
    assert len(dados["erros"]) == 2
    assert dados["serpapi"]["usadas_mes"] == 7 and dados["serpapi"]["limite_mensal"] == 240
    assert dados["tarefas"][0]["nome"] == "VooScanner" and dados["erro_tarefas"] is None


def test_obter_quando_o_schtasks_falha(tmp_path):
    def falha():
        raise OSError("schtasks não encontrado")

    dados = status.obter(tmp_path / "sem.log", tmp_path / "precos.db", {}, consultar_tarefas=falha)
    assert dados["tarefas"] == [] and "schtasks não encontrado" in dados["erro_tarefas"]
    assert dados["ultima_execucao"] is None and dados["erros"] == []
    assert dados["serpapi"]["limite_mensal"] == 240  # o mesmo padrão de main.saldo_serpapi
