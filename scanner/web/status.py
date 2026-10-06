"""Status para a interface: última execução e erros do log, cota da SerpApi e a tarefa agendada do Windows."""

import csv
import io
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from scanner import historico

NOMES_TAREFA = ("FlightScanner", "VooScanner")  # a tarefa instalada antes da troca de nome ainda é VooScanner
_INICIO_ENTRADA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ([A-Z]+) (.*)$")
_NIVEIS_DE_ERRO = ("WARNING", "ERROR", "CRITICAL")
JANELA_EXECUCAO = timedelta(minutes=20)


def ler_fim(caminho: Path, max_bytes: int = 200_000) -> list[str]:
    """As linhas do fim do arquivo (até max_bytes), sem a primeira se ela tiver sido cortada no meio."""
    try:
        with open(caminho, "rb") as f:
            tamanho = f.seek(0, io.SEEK_END)
            f.seek(max(0, tamanho - max_bytes))
            dados = f.read()
    except FileNotFoundError:
        return []
    linhas = dados.decode("utf-8", errors="replace").splitlines()
    if tamanho > max_bytes and linhas:
        linhas = linhas[1:]
    return linhas


def entradas(linhas: list[str]) -> list[dict]:
    """Uma entrada por registro do log (quando, nível, mensagem); linhas sem data (traceback, texto do
    alerta) continuam a mensagem anterior."""
    resultado = []
    for linha in linhas:
        m = _INICIO_ENTRADA.match(linha)
        if m:
            quando = m.group(1).replace(" ", "T")
            resultado.append({"quando": quando, "nivel": m.group(2), "mensagem": m.group(3)})
        elif resultado:
            resultado[-1]["mensagem"] += "\n" + linha
    return resultado


def ultima_execucao(registros: list[dict]) -> dict | None:
    """Último "Início:" e o "Fim:" depois dele (None se ainda está rodando ou foi interrompida)."""
    for i in range(len(registros) - 1, -1, -1):
        if registros[i]["mensagem"].startswith("Início:"):
            fim = next((r for r in registros[i + 1:] if r["mensagem"].startswith("Fim:")), None)
            return {
                "inicio": registros[i]["quando"], "inicio_texto": registros[i]["mensagem"],
                "fim": fim and fim["quando"], "fim_texto": fim and fim["mensagem"],
            }
    return None


def execucao_em_andamento(caminho_log: Path, agora: datetime | None = None) -> datetime | None:
    """Início da execução do scanner que está rodando agora (a agendada, ou outra), pelo log; None se não há.
    Uma execução leva um ou dois minutos: um "Início" sem "Fim" mais antigo que JANELA_EXECUCAO foi interrompido."""
    ultima = ultima_execucao(entradas(ler_fim(caminho_log)))
    if not ultima or ultima["fim"]:
        return None
    inicio = datetime.fromisoformat(ultima["inicio"])
    return inicio if (agora or datetime.now()) - inicio < JANELA_EXECUCAO else None


def erros_recentes(registros: list[dict], n: int = 10) -> list[dict]:
    return [r for r in reversed(registros) if r["nivel"] in _NIVEIS_DE_ERRO][:n]


def _data(texto: str) -> str | None:
    """'05/10/2026 21:08:43' → '2026-10-05T21:08:43'; 'N/A' e o que não for data → None."""
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y %H:%M:%S").isoformat()
    except ValueError:
        return None


def ler_schtasks(texto: str) -> list[dict]:
    """Lê a saída de `schtasks /query /fo csv /v`. Os títulos das colunas mudam com o idioma do Windows,
    então as colunas são lidas pela posição. Cada gatilho vira uma linha; a próxima execução é a menor."""
    tarefas: dict[str, dict] = {}
    for col in csv.reader(io.StringIO(texto)):
        if len(col) < 12:
            continue
        nome = col[1].rsplit("\\", 1)[-1]
        if nome not in NOMES_TAREFA:
            continue
        proxima = _data(col[2])
        tarefa = tarefas.setdefault(nome, {
            "nome": nome, "status": col[3], "situacao": col[11], "proxima": proxima,
            "ultima": _data(col[5]), "ultimo_resultado": col[6],
        })
        if proxima and (tarefa["proxima"] is None or proxima < tarefa["proxima"]):
            tarefa["proxima"] = proxima
    return list(tarefas.values())


def consultar_tarefas() -> list[dict]:
    resultado = subprocess.run(
        ["schtasks", "/query", "/fo", "csv", "/v"], capture_output=True, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    # O schtasks escreve na página de código do console (cp850 no Windows em português).
    texto = resultado.stdout.decode("oem" if sys.platform == "win32" else "utf-8", errors="replace")
    if resultado.returncode != 0:
        raise RuntimeError(f"schtasks terminou com o código {resultado.returncode}")
    return ler_schtasks(texto)


def obter(caminho_log: Path, caminho_banco: Path, geral: dict,
          consultar_tarefas: Callable[[], list[dict]] = consultar_tarefas) -> dict:
    registros = entradas(ler_fim(caminho_log))
    agora = datetime.now()
    con = historico.abrir(caminho_banco)
    try:
        serpapi = {
            "usadas_mes": historico.serpapi_usadas(con, agora),
            "usadas_hoje": historico.serpapi_usadas(con, agora, no_dia=True),
            "limite_mensal": geral.get("serpapi", {}).get("limite_mensal", 240),
        }
    finally:
        con.close()
    try:
        tarefas, erro_tarefas = consultar_tarefas(), None
    except Exception as erro:
        tarefas, erro_tarefas = [], f"Não consegui consultar a tarefa agendada: {erro}"
    return {
        "ultima_execucao": ultima_execucao(registros),
        "erros": erros_recentes(registros),
        "serpapi": serpapi,
        "tarefas": tarefas,
        "erro_tarefas": erro_tarefas,
    }
