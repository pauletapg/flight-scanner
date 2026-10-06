"""Quem pode falar com a interface.

- Modo local (padrão): só o navegador do próprio PC. Vale o IP de origem (loopback) e o cabeçalho Host (127.0.0.1,
  localhost ou ::1); este segundo barra o DNS rebinding, em que uma página de outro site faz o nome dela apontar
  para o PC. Qualquer outro pedido recebe 403, mesmo que alguém suba o uvicorn em 0.0.0.0 sem querer.
- Modo rede (atalho com --rede): além do PC, entra quem tem o token. Ele vem uma vez na URL (?t=...), vira um
  cookie HttpOnly e some da barra de endereços (redirecionamento). Sem token: 401.
- Em qualquer modo, ações que gravam (POST, PUT...) só valem se vierem da própria página: cabeçalho X-Flight-Scanner
  (que um site de fora não consegue mandar sem a permissão do navegador) e, quando o navegador informa, Origin
  igual ao Host e Sec-Fetch-Site same-origin. É a proteção contra CSRF."""

import ipaddress
import os
import secrets
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

VARIAVEL_TOKEN = "INTERFACE_TOKEN"
TAMANHO_MINIMO_TOKEN = 20
NOME_COOKIE = "flight_scanner_token"
CABECALHO_CSRF = "X-Flight-Scanner"
VALIDADE_COOKIE = 30 * 24 * 3600  # 30 dias; para trocar o token, apague a linha INTERFACE_TOKEN do .env

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}

# O app.js põe style="width: ..." nos medidores, então só o estilo aceita inline; script, nunca.
POLITICA_DE_CONTEUDO = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")

MSG_SO_NESTE_PC = "Esta interface só responde neste computador. Para abrir no celular, use o atalho com --rede."
MSG_SEM_TOKEN = ("Acesso negado: falta o token. Abra o endereço completo que aparece na tela de status da interface "
                 "(no PC), o que termina com ?t=...")
MSG_CSRF = "Pedido recusado: só a própria página da interface pode fazer esta ação, não outra página."


# --- token no .env -------------------------------------------------------------------------------------------

def garantir_token(arquivo: Path) -> str:
    """O INTERFACE_TOKEN do .env; se não houver (ou estiver vazio), gera um aleatório e grava, sem mexer no resto."""
    texto = ""
    if arquivo.exists():
        with open(arquivo, encoding="utf-8", newline="") as f:  # newline="": no Windows, read_text trocaria \r\n por \n
            texto = f.read()
    fim = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines(keepends=True)
    posicao = None
    for i, linha in enumerate(linhas):
        nome, igual, valor = linha.partition("=")
        if igual and nome.strip() == VARIAVEL_TOKEN:
            valor = valor.strip().strip("\"'")
            if len(valor) >= TAMANHO_MINIMO_TOKEN:
                return valor
            if valor:
                raise ValueError(f"O {VARIAVEL_TOKEN} do .env tem menos de {TAMANHO_MINIMO_TOKEN} caracteres: "
                                 "apague a linha para o programa gerar um token forte.")
            posicao = i
            break
    token = secrets.token_urlsafe(32)
    nova = f"{VARIAVEL_TOKEN}={token}{fim}"
    if posicao is not None:
        linhas[posicao] = nova
    else:
        if linhas and not linhas[-1].endswith(("\n", "\r")):
            linhas[-1] += fim
        linhas.append(nova)
    _gravar("".join(linhas), arquivo)
    return token


def _gravar(texto: str, arquivo: Path) -> None:
    """Arquivo temporário + os.replace, como o config.yaml: o .env tem as chaves, não pode ficar pela metade."""
    fd, temporario = tempfile.mkstemp(dir=arquivo.parent, prefix=".env-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        os.replace(temporario, arquivo)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)


# --- endereços do PC na rede -----------------------------------------------------------------------------------

def _ip_de_saida() -> list[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP não envia nada: só faz o sistema escolher a placa de saída
            return [s.getsockname()[0]]
    except OSError:
        return []


def _ips_do_nome() -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


def enderecos_locais() -> list[str]:
    """IPv4 de rede privada deste PC, o da rota de saída primeiro. Fora ficam loopback, link-local (169.254),
    CGNAT (100.64, usado por VPN) e públicos: o celular não chegaria por eles. Com VPN e máquinas virtuais,
    pode haver mais de uma placa; a tela de status mostra todas."""
    achados: list[str] = []
    for ip in _ip_de_saida() + _ips_do_nome():
        try:
            endereco = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (endereco.is_private and not (endereco.is_loopback or endereco.is_link_local or endereco.is_unspecified)
                and ip not in achados):
            achados.append(ip)
    return achados


# --- quem é o próprio PC -----------------------------------------------------------------------------------------

def _origem_local(ip: str | None) -> bool:
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    if endereco.version == 6 and endereco.ipv4_mapped:
        endereco = endereco.ipv4_mapped
    return endereco.is_loopback


def _host_local(host: str) -> bool:
    nome = host.strip().lower()
    if nome.startswith("["):  # [::1]:8765
        nome = nome[1:].partition("]")[0]
    elif nome.count(":") == 1:  # 127.0.0.1:8765
        nome = nome.partition(":")[0]
    return nome in HOSTS_LOCAIS


def _confere(candidato: str | None, token: str) -> bool:
    # Em bytes: compare_digest com str recusa texto fora do ASCII, e a URL é de quem chama.
    return bool(candidato) and secrets.compare_digest(candidato.encode("utf-8"), token.encode("utf-8"))


# --- o filtro de cada requisição -----------------------------------------------------------------------------------

def _negar(request: Request, codigo: int, mensagem: str) -> Response:
    if request.url.path.startswith("/api/"):
        resposta = JSONResponse({"detail": mensagem}, codigo)
    else:
        resposta = HTMLResponse(
            '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>Flight Scanner</title>'
            f"<h1>Flight Scanner</h1><p>{mensagem}</p></html>", codigo)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _entrar(request: Request, token: str) -> Response:
    """Token certo na URL: guarda no cookie e volta para a mesma página sem ele (não fica na barra de endereços,
    no histórico nem no Referer)."""
    resto = [(k, v) for k, v in request.query_params.multi_items() if k != "t"]
    destino = "/" + request.url.path.lstrip("/")  # nunca "//outro-site": o redirecionamento fica neste site
    if resto:
        destino += "?" + urlencode(resto)
    resposta = RedirectResponse(destino, status_code=303)
    resposta.set_cookie(NOME_COOKIE, token, max_age=VALIDADE_COOKIE, httponly=True, samesite="lax", path="/")
    return resposta


def _recusa_csrf(request: Request) -> str | None:
    if not request.headers.get(CABECALHO_CSRF):
        return MSG_CSRF
    origem = request.headers.get("origin")
    if origem is not None and urlsplit(origem).netloc.lower() != request.headers.get("host", "").lower():
        return MSG_CSRF  # inclui Origin: null
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return MSG_CSRF  # cross-site, ou same-site de outra porta
    return None


async def _filtrar(request: Request, call_next, token: str | None) -> Response:
    do_pc = _origem_local(request.client.host if request.client else None) and _host_local(request.headers.get("host", ""))
    if not do_pc:
        if token is None:
            return _negar(request, 403, MSG_SO_NESTE_PC)
        if not _confere(request.cookies.get(NOME_COOKIE), token):
            if request.method in ("GET", "HEAD") and _confere(request.query_params.get("t"), token):
                return _entrar(request, token)
            return _negar(request, 401, MSG_SEM_TOKEN)
    if request.method not in METODOS_SEGUROS:
        motivo = _recusa_csrf(request)
        if motivo:
            return _negar(request, 403, motivo)
    return await call_next(request)


def instalar(app: FastAPI, token: str | None) -> None:
    """Liga o filtro de acesso. token=None é o modo local; com token, o modo rede."""

    @app.middleware("http")
    async def controlar_acesso(request: Request, call_next):
        resposta = await _filtrar(request, call_next, token)
        resposta.headers["Content-Security-Policy"] = POLITICA_DE_CONTEUDO
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"  # as respostas da API nunca ficam guardadas
        return resposta
