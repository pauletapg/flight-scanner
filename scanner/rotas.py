"""Rotas monitoradas no config.yaml: listar, adicionar, editar, pausar, retomar e remover.

Usado pela CLI (scanner.buscar) e pela interface. O arquivo é editado por blocos de texto, um por rota,
para preservar os comentários; antes de gravar, o YAML é validado e a gravação é atômica (arquivo
temporário + os.replace), porque a tarefa agendada pode estar lendo o config ao mesmo tempo."""

import os
import tempfile
import time
from pathlib import Path

import yaml

from scanner.main import MAX_ROTAS, PASTA

CAMINHO_CONFIG = PASTA / "config.yaml"


class ErroRota(Exception):
    """Base dos erros de edição das rotas; a mensagem já vem em português."""


class RotaNaoEncontrada(ErroRota):
    def __init__(self, nome: str, nomes: list[str]):
        super().__init__(f"Não achei a busca {nome!r}.")
        self.nome, self.nomes = nome, nomes


class NomeRepetido(ErroRota):
    def __init__(self, nome: str):
        super().__init__(f"Já existe uma rota chamada {nome!r} no config.yaml.")
        self.nome = nome


class VagasEsgotadas(ErroRota):
    def __init__(self, ativas: list[str]):
        super().__init__(f"Já há {MAX_ROTAS} buscas monitoradas (o máximo).")
        self.ativas = ativas


def _ler(caminho: Path | None) -> tuple[Path, str, bool, list[dict]]:
    """(caminho, texto com '\\n', se o arquivo usa CRLF, rotas). Sem caminho, usa o config.yaml do projeto."""
    caminho = caminho or CAMINHO_CONFIG
    texto = caminho.read_bytes().decode("utf-8")
    crlf = "\r\n" in texto
    texto = texto.replace("\r\n", "\n")
    return caminho, texto, crlf, yaml.safe_load(texto)["rotas"] or []


def _gravar(caminho: Path, texto: str, crlf: bool) -> None:
    yaml.safe_load(texto)  # garante que o arquivo continua válido antes de gravar
    fd, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".config-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8", newline="\r\n" if crlf else "\n") as f:
            f.write(texto)
        for tentativa in range(5):  # no Windows, falha se outro processo estiver lendo neste instante
            try:
                os.replace(temporario, caminho)
                return
            except PermissionError:
                if tentativa == 4:
                    raise
                time.sleep(0.2)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)


def _blocos(texto: str) -> tuple[str, list[str]]:
    """Separa o config.yaml em (cabeçalho até 'rotas:', um texto por rota), preservando os comentários."""
    linhas = texto.splitlines(keepends=True)
    inicio = next(i for i, l in enumerate(linhas) if l.startswith("rotas:")) + 1
    blocos: list[str] = []
    for linha in linhas[inicio:]:
        if linha.startswith("  - "):
            blocos.append(linha)
        elif blocos:
            blocos[-1] += linha
    return "".join(linhas[:inicio]), blocos


def _montar(cabecalho: str, blocos: list[str]) -> str:
    return cabecalho + "".join("\n" + b.strip("\n") + "\n" for b in blocos)


def _bloco(rota: dict) -> str:
    texto = yaml.safe_dump([rota], allow_unicode=True, sort_keys=False, default_flow_style=None)
    return "".join("  " + linha for linha in texto.splitlines(keepends=True))


def _com_pausa(bloco: str, pausada: bool) -> str:
    linhas = [l for l in bloco.splitlines(keepends=True) if not l.strip().startswith("pausada:")]
    if pausada:
        linhas.insert(1, "    pausada: true\n")
    return "".join(linhas)


def _ativas(rotas: list[dict]) -> list[dict]:
    return [r for r in rotas if not r.get("pausada")]


def _indice(rotas: list[dict], nome: str) -> int:
    for i, r in enumerate(rotas):
        if r["nome"] == nome:
            return i
    raise RotaNaoEncontrada(nome, [r["nome"] for r in rotas])


def listar(caminho: Path | None = None) -> list[dict]:
    return _ler(caminho)[3]


def adicionar(rota: dict, substituir: str | None = None, caminho: Path | None = None) -> None:
    """Acrescenta a rota no fim. Com MAX_ROTAS ativas, só entra substituindo uma delas (`substituir`)."""
    caminho, texto, crlf, rotas = _ler(caminho)
    if any(r["nome"] == rota["nome"] for r in rotas):
        raise NomeRepetido(rota["nome"])
    cabecalho, blocos = _blocos(texto)
    if substituir is not None:
        i = _indice(rotas, substituir)
        del blocos[i], rotas[i]
    if not rota.get("pausada") and len(_ativas(rotas)) >= MAX_ROTAS:
        raise VagasEsgotadas([r["nome"] for r in _ativas(rotas)])
    blocos.append(_bloco(rota))
    _gravar(caminho, _montar(cabecalho, blocos), crlf)


def editar(nome_antigo: str, rota: dict, caminho: Path | None = None) -> None:
    """Troca a rota no mesmo lugar. O estado pausada/ativa não muda aqui (use pausar/retomar)."""
    caminho, texto, crlf, rotas = _ler(caminho)
    i = _indice(rotas, nome_antigo)
    if rota["nome"] != nome_antigo and any(r["nome"] == rota["nome"] for r in rotas):
        raise NomeRepetido(rota["nome"])
    cabecalho, blocos = _blocos(texto)
    nova = {k: v for k, v in rota.items() if k != "pausada"}
    blocos[i] = _com_pausa(_bloco(nova), bool(rotas[i].get("pausada")))
    _gravar(caminho, _montar(cabecalho, blocos), crlf)


def _mudar_pausa(nome: str, pausada: bool, caminho: Path | None) -> list[dict]:
    caminho, texto, crlf, rotas = _ler(caminho)
    i = _indice(rotas, nome)
    cabecalho, blocos = _blocos(texto)
    blocos[i] = _com_pausa(blocos[i], pausada)
    _gravar(caminho, _montar(cabecalho, blocos), crlf)
    rotas[i]["pausada"] = pausada
    return rotas


def pausar(nome: str, caminho: Path | None = None) -> None:
    _mudar_pausa(nome, True, caminho)


def retomar(nome: str, caminho: Path | None = None) -> int:
    """Reativa a rota e devolve quantas ficaram ativas (acima de MAX_ROTAS o scanner não roda)."""
    return len(_ativas(_mudar_pausa(nome, False, caminho)))


def remover(nome: str, caminho: Path | None = None) -> None:
    caminho, texto, crlf, rotas = _ler(caminho)
    i = _indice(rotas, nome)
    cabecalho, blocos = _blocos(texto)
    del blocos[i]
    _gravar(caminho, _montar(cabecalho, blocos), crlf)
