"""Trabalhos em segundo plano da interface: a busca avulsa (numa thread) e o "Rodar agora" (subprocesso
`python -m scanner.main`). Um de cada por vez; o estado fica em memória enquanto o servidor estiver aberto."""

import dataclasses
import os
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from scanner import busca_avulsa


class Ocupado(Exception):
    """Já há um trabalho do mesmo tipo rodando; a mensagem vai para a interface."""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def voo_em_dict(voo) -> dict:
    return dataclasses.asdict(voo) | {"menor_preco": voo.menor_preco}


class Buscas:
    """Buscas avulsas, uma por vez. `obter(id)` devolve uma cópia do estado: a rota (`config`), o progresso
    i/n, as linhas de progresso, os resultados (quando termina) e o erro (se der errado)."""

    def __init__(self):
        self._trava = threading.Lock()
        self._buscas: dict[str, dict] = {}
        self._rodando: str | None = None
        self._ultima: str | None = None

    def iniciar(self, rota: dict, geral: dict, n: int, reservas: int = 0, caminho_banco: Path | None = None) -> str:
        with self._trava:
            if self._rodando:
                raise Ocupado("Já há uma busca em andamento; espere ela terminar.")
            id_ = uuid.uuid4().hex[:12]
            self._buscas[id_] = {
                "id": id_, "rota": rota["nome"], "config": rota, "estado": "rodando", "i": 0, "n": n,
                "linhas": [], "resultados": [], "erro": None, "inicio": _agora(), "fim": None,
            }
            self._rodando = self._ultima = id_
        extras = {"caminho_banco": caminho_banco} if caminho_banco else {}
        threading.Thread(target=self._rodar, args=(id_, rota, geral, reservas, extras), daemon=True).start()
        return id_

    def _rodar(self, id_: str, rota: dict, geral: dict, reservas: int, extras: dict) -> None:
        busca = self._buscas[id_]

        def progresso(i, n, texto):
            with self._trava:
                if i is not None:
                    busca["i"], busca["n"] = i, n
                busca["linhas"].append({"i": i, "n": n, "texto": texto})

        try:
            voos = busca_avulsa.buscar(rota, geral, reservas=reservas, progresso=progresso, **extras)
            resultado = {"estado": "concluida", "resultados": [voo_em_dict(v) for v in voos]}
        except Exception as erro:
            resultado = {"estado": "erro", "erro": f"{type(erro).__name__}: {erro}"}
        with self._trava:
            busca.update(resultado, fim=_agora())
            self._rodando = None

    def atual(self) -> dict | None:
        """A busca em andamento ou, se nenhuma estiver rodando, a última (para a página retomar)."""
        return self._ultima and self.obter(self._ultima)

    def obter(self, id_: str) -> dict | None:
        with self._trava:
            busca = self._buscas.get(id_)
            return busca and {**busca, "linhas": list(busca["linhas"])}


class Execucoes:
    """O "Rodar agora": roda o scanner como a tarefa agendada roda, num processo separado, e guarda a saída."""

    def __init__(self, comando: list[str], pasta: Path):
        self.comando, self.pasta = comando, pasta
        self._trava = threading.Lock()
        self._ultima: dict | None = None

    def iniciar(self, dry_run: bool = False) -> dict:
        with self._trava:
            if self._ultima and self._ultima["estado"] == "rodando":
                raise Ocupado("O scanner já está rodando por aqui; espere terminar.")
            self._ultima = {"estado": "rodando", "dry_run": dry_run, "codigo": None, "saida": "",
                            "inicio": _agora(), "fim": None}
            execucao = self._ultima
        threading.Thread(target=self._rodar, args=(execucao,), daemon=True).start()
        return dict(execucao)

    def _rodar(self, execucao: dict) -> None:
        comando = self.comando + (["--dry-run"] if execucao["dry_run"] else [])
        try:
            processo = subprocess.run(
                comando, cwd=self.pasta, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30 * 60,
                env=os.environ | {"PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            codigo = processo.returncode
            saida = processo.stdout.decode("utf-8", errors="replace")
        except Exception as erro:  # timeout, executável não encontrado...
            codigo, saida = None, f"{type(erro).__name__}: {erro}"
        with self._trava:
            execucao.update(estado="concluida" if codigo == 0 else "erro", codigo=codigo, saida=saida, fim=_agora())

    def ultima(self) -> dict | None:
        with self._trava:
            return self._ultima and dict(self._ultima)
