"""Servidor da interface: API JSON em /api e os arquivos de scanner/web/static em /.

Rodar: .\\.venv\\Scripts\\python.exe -m uvicorn scanner.web.app:app --port 8765
A lógica fica nos mesmos módulos da CLI (rotas, busca_avulsa, relatorio, historico, notificar);
aqui só há a tradução para HTTP."""

import sys
from contextlib import asynccontextmanager, closing
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scanner import busca_avulsa, historico, notificar, relatorio, rotas
from scanner.busca_avulsa import LIMITE_SEM_CONFIRMAR
from scanner.main import CAMINHO_BANCO, MAX_ROTAS, PASTA
from scanner.web import status, tarefas

PASTA_STATIC = Path(__file__).resolve().parent / "static"
CAMINHO_LOG = PASTA / "logs" / "scanner.log"


# --- formato das rotas recebidas ------------------------------------------------------------------------

class Filtros(BaseModel):
    preco_max: int | None = Field(None, ge=1)
    escalas_max: int | None = Field(None, ge=0)
    duracao_max_horas: int | float | None = Field(None, gt=0)


class Alerta(BaseModel):
    queda_percentual: int | float = Field(10, gt=0, lt=100)


class RotaEntrada(BaseModel):
    """Os mesmos campos de uma rota do config.yaml (e das opções do scanner.buscar)."""
    nome: str | None = None
    origem: str = Field(min_length=3)
    destino: str = Field(min_length=3)
    ida_entre: tuple[date, date] | None = None
    passo_dias: int = Field(1, ge=1)
    datas: list[date | tuple[date, date]] | None = None
    duracoes_dias: list[int] | None = None
    adultos: int = Field(1, ge=1)
    criancas: int = Field(0, ge=0)
    bebes_colo: int = Field(0, ge=0)
    classe: Literal["economy", "premium-economy", "business", "first"] = "economy"
    filtros: Filtros = Filtros()
    alerta: Alerta = Alerta()


def montar_rota(e: RotaEntrada) -> dict:
    """A rota como fica no config.yaml, na mesma ordem de campos que o scanner.buscar grava."""
    if not (e.ida_entre or e.datas):
        raise HTTPException(422, "Informe as datas: um intervalo de ida (ida_entre) e/ou datas avulsas.")
    origem, destino = e.origem.strip().upper(), e.destino.strip().upper()
    rota = {"nome": (e.nome or "").strip() or f"{origem} → {destino}", "origem": origem, "destino": destino}
    if e.ida_entre:
        rota["ida_entre"] = list(e.ida_entre)
        rota["passo_dias"] = e.passo_dias
    if e.datas:
        rota["datas"] = [list(d) if isinstance(d, tuple) else d for d in e.datas]
    if e.duracoes_dias:
        rota["duracoes_dias"] = e.duracoes_dias
    rota |= {"adultos": e.adultos, "criancas": e.criancas, "bebes_colo": e.bebes_colo, "classe": e.classe}
    rota["filtros"] = e.filtros.model_dump(exclude_none=True)
    rota["alerta"] = {"queda_percentual": e.alerta.queda_percentual}
    return rota


class NovaRota(BaseModel):
    rota: RotaEntrada
    substituir: str | None = None


class EdicaoRota(BaseModel):
    nome: str
    rota: RotaEntrada


class AcaoRota(BaseModel):
    nome: str
    acao: Literal["pausar", "retomar", "remover"]


class PedidoBusca(BaseModel):
    rota: RotaEntrada
    reservas: int = Field(0, ge=0)
    forcar: bool = False


class PedidoExecucao(BaseModel):
    dry_run: bool = False


_ERROS_PYDANTIC = {
    "missing": "campo obrigatório",
    "greater_than_equal": "precisa ser no mínimo {ge}",
    "greater_than": "precisa ser maior que {gt}",
    "less_than": "precisa ser menor que {lt}",
    "string_too_short": "precisa ter pelo menos {min_length} caracteres",
    "literal_error": "use um destes: {expected}",
}


def _mensagem_validacao(erro: dict) -> str:
    campo = ".".join(str(p) for p in erro["loc"] if p != "body")
    modelo = _ERROS_PYDANTIC.get(erro["type"], "valor inválido")
    return f"Dados inválidos em {campo}: {modelo.format(**erro.get('ctx', {}))}"


# --- aplicação --------------------------------------------------------------------------------------------

def _comando_padrao() -> list[str]:
    # Com o servidor aberto por pythonw (sem console), o scanner roda com o python.exe ao lado, para a saída
    # ir para o pipe; a janela não aparece por causa do CREATE_NO_WINDOW em tarefas.Execucoes.
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").exists():
        python = python.with_name("python.exe")
    return [str(python), "-m", "scanner.main"]


def criar_app(caminho_config: Path | None = None, caminho_banco: Path = CAMINHO_BANCO,
              caminho_log: Path = CAMINHO_LOG, consultar_tarefas=status.consultar_tarefas,
              comando_scanner: list[str] | None = None, arquivo_env: Path | None = None) -> FastAPI:
    """Sem caminho_config, usa rotas.CAMINHO_CONFIG (lido na hora de cada requisição)."""

    @asynccontextmanager
    async def ciclo(app):
        if arquivo_env:
            load_dotenv(arquivo_env)  # chaves do ntfy e da SerpApi, como no scanner.main
        yield

    app = FastAPI(title="Flight Scanner", lifespan=ciclo)
    buscas = tarefas.Buscas()
    execucoes = tarefas.Execucoes(comando_scanner or _comando_padrao(), PASTA)

    def geral() -> dict:
        return yaml.safe_load((caminho_config or rotas.CAMINHO_CONFIG).read_text(encoding="utf-8"))["geral"]

    def banco():
        return closing(historico.abrir(caminho_banco))

    @app.exception_handler(rotas.ErroRota)
    def _erro_rota(request, erro: rotas.ErroRota):
        corpo = {"detail": str(erro)}
        if isinstance(erro, rotas.RotaNaoEncontrada):
            return JSONResponse(corpo | {"nomes": erro.nomes}, 404)
        if isinstance(erro, rotas.VagasEsgotadas):
            return JSONResponse(corpo | {"ativas": erro.ativas}, 409)
        if isinstance(erro, rotas.NomeRepetido):
            return JSONResponse(corpo, 409)
        return JSONResponse(corpo, 422)

    @app.exception_handler(tarefas.Ocupado)
    def _ocupado(request, erro: tarefas.Ocupado):
        return JSONResponse({"detail": str(erro)}, 409)

    @app.exception_handler(RequestValidationError)
    def _invalido(request, erro: RequestValidationError):
        return JSONResponse({"detail": _mensagem_validacao(erro.errors()[0])}, 422)

    # --- rotas monitoradas ---

    @app.get("/api/rotas")
    def listar_rotas():
        lista = [r | {"pausada": bool(r.get("pausada"))} for r in rotas.listar(caminho_config)]
        ativas = sum(not r["pausada"] for r in lista)
        return {"rotas": jsonable_encoder(lista), "ativas": ativas, "max_ativas": MAX_ROTAS}

    @app.post("/api/rotas", status_code=201)
    def adicionar_rota(pedido: NovaRota):
        rota = montar_rota(pedido.rota)
        rotas.adicionar(rota, substituir=pedido.substituir, caminho=caminho_config)
        return {"nome": rota["nome"]}

    @app.put("/api/rotas")
    def editar_rota(pedido: EdicaoRota):
        rota = montar_rota(pedido.rota)
        rotas.editar(pedido.nome, rota, caminho=caminho_config)
        return {"nome": rota["nome"]}

    @app.post("/api/rotas/acao")
    def acao_rota(pedido: AcaoRota):
        if pedido.acao == "retomar":
            # A CLI só avisa; a interface recusa, para nunca deixar mais de MAX_ROTAS ativas.
            lista = rotas.listar(caminho_config)
            ativas = [r["nome"] for r in lista if not r.get("pausada")]
            pausada = any(r["nome"] == pedido.nome and r.get("pausada") for r in lista)
            if pausada and len(ativas) >= MAX_ROTAS:
                raise rotas.VagasEsgotadas(ativas)
            return {"ativas": rotas.retomar(pedido.nome, caminho=caminho_config)}
        {"pausar": rotas.pausar, "remover": rotas.remover}[pedido.acao](pedido.nome, caminho=caminho_config)
        return {"ok": True}

    # --- busca avulsa ---

    @app.post("/api/busca", status_code=202)
    def iniciar_busca(pedido: PedidoBusca):
        rota = montar_rota(pedido.rota)
        n = len(busca_avulsa.combinacoes_da_rota(rota))
        if not n:
            raise HTTPException(422, "Nenhuma data no futuro para buscar.")
        if n > LIMITE_SEM_CONFIRMAR and not pedido.forcar:
            raise HTTPException(422, f"São {n} buscas; muitas de uma vez podem bloquear o Google. "
                                     f"Reduza as datas ou confirme para buscar mesmo assim.")
        id_ = buscas.iniciar(rota, geral(), n, reservas=pedido.reservas, caminho_banco=caminho_banco)
        return {"id": id_, "n": n, "rota": jsonable_encoder(rota)}

    @app.get("/api/busca/{id_}")
    def ver_busca(id_: str):
        busca = buscas.obter(id_)
        if busca is None:
            raise HTTPException(404, "Busca não encontrada (o servidor pode ter sido reiniciado).")
        return jsonable_encoder(busca)

    # --- histórico ---

    @app.get("/api/historico")
    def ver_historico(rota: str | None = None):
        with banco() as con:
            nomes = [n for (n,) in con.execute("SELECT DISTINCT rota FROM precos ORDER BY rota")]
            pontos = []
            if rota:
                linhas = con.execute(
                    "SELECT buscado_em, ida, volta, MIN(preco), MIN(CASE WHEN passa_filtros THEN preco END) "
                    "FROM precos WHERE rota = ? GROUP BY buscado_em, ida, volta ORDER BY buscado_em, ida, volta",
                    (rota,),
                )
                pontos = [{"buscado_em": b, "ida": i, "volta": v, "menor_preco": p, "menor_nos_filtros": f}
                          for b, i, v, p, f in linhas]
        return {"rotas": nomes, "rota": rota, "pontos": pontos}

    @app.get("/api/alertas")
    def ver_alertas(rota: str | None = None, limite: int = 100):
        with banco() as con:
            linhas = con.execute(
                "SELECT enviado_em, rota, ida, volta, companhias, preco FROM alertas "
                "WHERE ? IS NULL OR rota = ? ORDER BY enviado_em DESC LIMIT ?",
                (rota, rota, limite),
            ).fetchall()
        campos = ("enviado_em", "rota", "ida", "volta", "companhias", "preco")
        return [dict(zip(campos, linha)) for linha in linhas]

    @app.get("/api/relatorio")
    def ver_relatorio():
        with banco() as con:
            return {"texto": relatorio.gerar(con), "rotas": relatorio.dados(con)}

    # --- status e ações ---

    @app.get("/api/status")
    def ver_status():
        return status.obter(caminho_log, caminho_banco, geral(), consultar_tarefas) | {"execucao": execucoes.ultima()}

    @app.post("/api/executar", status_code=202)
    def executar(pedido: PedidoExecucao):
        return execucoes.iniciar(pedido.dry_run)

    @app.get("/api/executar")
    def ver_execucao():
        return execucoes.ultima()

    @app.post("/api/notificacao-teste")
    def notificacao_teste():
        try:
            notificar.enviar_teste()
        except notificar.SemCredenciais as erro:
            raise HTTPException(422, f"Notificação não configurada: {erro}.")
        except Exception as erro:
            raise HTTPException(502, f"Falha ao enviar a notificação: {erro}")
        return {"ok": True}

    app.mount("/", StaticFiles(directory=PASTA_STATIC, html=True), name="static")
    return app


app = criar_app(arquivo_env=PASTA / ".env")
