"""Acesso pela rede (Etapa 7): token, cookie, bloqueio de quem não é o próprio PC e proteção contra CSRF."""

import pytest

from scanner.web import acesso, app as web

TOKEN = "t" * 20 + "-token-de-teste-bem-comprido"
CELULAR = {"ip": "192.168.2.50", "host": "192.168.2.242:8765"}  # outro aparelho da rede chamando o PC

CONFIG = """\
geral:
  moeda: BRL
  serpapi:
    limite_mensal: 200

rotas:

  - nome: A
    origem: RIO
    destino: REC
    datas: [2026-12-20]
    adultos: 1
    criancas: 0
    bebes_colo: 0
    classe: economy
"""


@pytest.fixture
def app_local(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return web.criar_app(caminho_config=config, caminho_banco=tmp_path / "precos.db",
                         caminho_log=tmp_path / "scanner.log", consultar_tarefas=lambda: [])


@pytest.fixture
def app_rede(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return web.criar_app(caminho_config=config, caminho_banco=tmp_path / "precos.db",
                         caminho_log=tmp_path / "scanner.log", consultar_tarefas=lambda: [], token=TOKEN)


# --- token no .env -----------------------------------------------------------------------------------------

def test_garantir_token_cria_o_arquivo_e_reaproveita_o_token(tmp_path):
    env = tmp_path / ".env"
    token = acesso.garantir_token(env)
    assert len(token) >= 32
    assert env.read_text(encoding="utf-8") == f"INTERFACE_TOKEN={token}\n"
    assert acesso.garantir_token(env) == token  # na segunda vez não gera outro
    assert env.read_text(encoding="utf-8").count("INTERFACE_TOKEN") == 1


def test_garantir_token_preserva_o_resto_do_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# chaves\nNTFY_TOPIC=segredo\nSERPAPI_KEY=abc", encoding="utf-8", newline="")  # sem \n no fim
    token = acesso.garantir_token(env)
    assert env.read_text(encoding="utf-8") == f"# chaves\nNTFY_TOPIC=segredo\nSERPAPI_KEY=abc\nINTERFACE_TOKEN={token}\n"


def test_garantir_token_mantem_o_fim_de_linha_crlf(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"NTFY_TOPIC=x\r\n")
    token = acesso.garantir_token(env)
    assert env.read_bytes() == f"NTFY_TOPIC=x\r\nINTERFACE_TOKEN={token}\r\n".encode()


def test_garantir_token_preenche_a_linha_vazia(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nINTERFACE_TOKEN=\nB=2\n", encoding="utf-8")
    token = acesso.garantir_token(env)
    assert env.read_text(encoding="utf-8") == f"A=1\nINTERFACE_TOKEN={token}\nB=2\n"


def test_garantir_token_recusa_token_fraco(tmp_path):
    env = tmp_path / ".env"
    env.write_text("INTERFACE_TOKEN=1234\n", encoding="utf-8")
    with pytest.raises(ValueError, match="INTERFACE_TOKEN"):
        acesso.garantir_token(env)
    assert env.read_text(encoding="utf-8") == "INTERFACE_TOKEN=1234\n"  # não sobrescreve o que a pessoa pôs


def test_garantir_token_aceita_token_com_aspas(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f'INTERFACE_TOKEN="{TOKEN}"\n', encoding="utf-8")
    assert acesso.garantir_token(env) == TOKEN


# --- endereços do PC ------------------------------------------------------------------------------------------

def test_enderecos_locais_so_redes_privadas_sem_repetir(monkeypatch):
    class Soquete:
        def __enter__(self):
            return self

        def __exit__(self, *erro):
            return False

        def connect(self, destino):
            pass

        def getsockname(self):
            return ("192.168.2.242", 5000)

    monkeypatch.setattr(acesso.socket, "socket", lambda *a: Soquete())
    nomes = ["127.0.0.1", "192.168.56.1", "192.168.2.242", "169.254.10.1", "100.64.1.1", "8.8.8.8", "10.5.0.2"]
    monkeypatch.setattr(acesso.socket, "getaddrinfo", lambda *a: [(2, 1, 6, "", (ip, 0)) for ip in nomes])
    # o da rota de saída vem primeiro; sem loopback, link-local, CGNAT (VPN) nem endereço público
    assert acesso.enderecos_locais() == ["192.168.2.242", "192.168.56.1", "10.5.0.2"]


def test_enderecos_locais_sem_rede_devolve_lista_vazia(monkeypatch):
    def falha(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr(acesso.socket, "socket", falha)
    monkeypatch.setattr(acesso.socket, "getaddrinfo", falha)
    assert acesso.enderecos_locais() == []


# --- modo local (sem --rede): só o próprio PC ------------------------------------------------------------------

def test_modo_local_atende_o_navegador_do_pc(app_local, abrir_cliente):
    cliente = abrir_cliente(app_local)
    assert cliente.get("/api/rotas").status_code == 200
    assert cliente.get("/").status_code == 200
    assert cliente.get("/api/acesso").json() == {"rede": False}


def test_modo_local_atende_localhost_e_ipv6(app_local, abrir_cliente):
    assert abrir_cliente(app_local, host="localhost:8765").get("/api/rotas").status_code == 200
    assert abrir_cliente(app_local, ip="::1", host="[::1]:8765").get("/api/rotas").status_code == 200
    assert abrir_cliente(app_local, ip="::ffff:127.0.0.1").get("/api/rotas").status_code == 200


def test_modo_local_recusa_outro_aparelho_mesmo_com_token(app_local, abrir_cliente):
    """Se alguém subir o uvicorn em 0.0.0.0 sem --rede, a rede não pode entrar."""
    cliente = abrir_cliente(app_local, **CELULAR)
    for caminho in ("/api/rotas", "/", f"/api/rotas?t={TOKEN}"):
        r = cliente.get(caminho)
        assert r.status_code == 403, caminho
        assert "só responde neste computador" in r.text


def test_modo_local_recusa_host_estranho_dns_rebinding(app_local, abrir_cliente):
    """Uma página de outro site que 'vira' o endereço do PC (DNS rebinding) chega com o Host dela."""
    r = abrir_cliente(app_local, host="site-malicioso.com:8765").get("/api/rotas")
    assert r.status_code == 403


# --- modo rede (--rede): token ----------------------------------------------------------------------------------

def test_modo_rede_sem_token_responde_401(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, **CELULAR)
    r = cliente.get("/api/rotas")
    assert r.status_code == 401 and "token" in r.json()["detail"]
    pagina = cliente.get("/")
    assert pagina.status_code == 401 and "text/html" in pagina.headers["content-type"] and "token" in pagina.text
    assert cliente.get("/app.js").status_code == 401  # nem os arquivos da página
    assert cliente.post("/api/executar", json={}).status_code == 401


def test_modo_rede_token_errado_responde_401(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, follow_redirects=False, **CELULAR)
    assert cliente.get("/?t=errado").status_code == 401
    assert cliente.get(f"/?t={TOKEN[:-1]}").status_code == 401  # quase certo
    assert cliente.get("/?t=" + "ç" * 5).status_code == 401  # fora do ASCII não pode derrubar a comparação
    assert "set-cookie" not in cliente.get("/?t=errado").headers


def test_modo_rede_token_na_url_vira_cookie_e_some_da_barra_de_enderecos(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, follow_redirects=False, **CELULAR)
    r = cliente.get(f"/?t={TOKEN}#status")
    assert r.status_code == 303 and r.headers["location"] == "/"  # sem o token na URL
    cookie = r.headers["set-cookie"]
    assert f"{acesso.NOME_COOKIE}={TOKEN}" in cookie
    # Lax (e não Strict): um link aberto de outro app, como o WhatsApp, ainda entra; POST de outro site não leva o cookie
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower() and "Path=/" in cookie and "Max-Age=" in cookie
    # com o cookie guardado, o resto funciona sem token na URL
    assert cliente.get("/api/rotas").status_code == 200
    assert cliente.get("/").status_code == 200


def test_modo_rede_redirecionamento_guarda_o_caminho_e_o_resto_da_consulta(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, follow_redirects=False, **CELULAR)
    r = cliente.get(f"/api/historico?rota=A&t={TOKEN}&limite=5")
    assert r.status_code == 303 and r.headers["location"] == "/api/historico?rota=A&limite=5"


def test_modo_rede_redirecionamento_nunca_sai_do_site(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, follow_redirects=False, **CELULAR)
    r = cliente.get(f"//site-malicioso.com/?t={TOKEN}")
    assert r.status_code == 303 and r.headers["location"].startswith("/") and not r.headers["location"].startswith("//")


def test_modo_rede_cookie_errado_responde_401(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, cabecalhos={"Cookie": f"{acesso.NOME_COOKIE}=errado"}, **CELULAR)
    assert cliente.get("/api/rotas").status_code == 401


def test_modo_rede_token_so_vale_na_url_de_leituras(app_rede, abrir_cliente):
    """Em POST o token na URL não autentica (iria parar em logs e no histórico do navegador)."""
    cliente = abrir_cliente(app_rede, **CELULAR)
    r = cliente.post(f"/api/executar?t={TOKEN}", json={"dry_run": True})
    assert r.status_code == 401


def test_modo_rede_o_proprio_pc_dispensa_o_token(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede)
    assert cliente.get("/api/rotas").status_code == 200
    assert cliente.get("/").status_code == 200


def test_modo_rede_pc_com_host_estranho_precisa_do_token(app_rede, abrir_cliente):
    """Mesmo vindo do 127.0.0.1, o Host de outro site (DNS rebinding) não é o navegador do PC."""
    r = abrir_cliente(app_rede, host="site-malicioso.com:8765").get("/api/rotas")
    assert r.status_code == 401


def test_modo_rede_acessar_o_pc_pelo_ip_da_rede_tambem_pede_token(app_rede, abrir_cliente):
    cliente = abrir_cliente(app_rede, ip="192.168.2.242", host="192.168.2.242:8765")  # o PC abrindo o endereço da rede
    assert cliente.get("/api/rotas").status_code == 401


# --- endereço mostrado na tela de status -----------------------------------------------------------------------

def test_api_acesso_no_modo_rede_traz_o_endereco_com_o_token(app_rede, abrir_cliente, monkeypatch):
    monkeypatch.setattr(acesso, "enderecos_locais", lambda: ["192.168.2.242", "10.5.0.2"])
    dados = abrir_cliente(app_rede).get("/api/acesso").json()
    assert dados["rede"] is True and dados["porta"] == 8765
    assert dados["enderecos"] == [
        {"ip": "192.168.2.242", "url": f"http://192.168.2.242:8765/?t={TOKEN}"},
        {"ip": "10.5.0.2", "url": f"http://10.5.0.2:8765/?t={TOKEN}"},
    ]


def test_api_acesso_exige_token_de_quem_vem_da_rede(app_rede, abrir_cliente):
    assert abrir_cliente(app_rede, **CELULAR).get("/api/acesso").status_code == 401


# --- CSRF: ações que gravam ---------------------------------------------------------------------------------------

def test_post_sem_o_cabecalho_da_pagina_e_recusado(app_local, abrir_cliente):
    cliente = abrir_cliente(app_local, csrf=False)
    for chamada in (lambda: cliente.post("/api/notificacao-teste"), lambda: cliente.post("/api/executar", json={}),
                    lambda: cliente.put("/api/rotas", json={}), lambda: cliente.delete("/api/rotas")):
        r = chamada()
        assert r.status_code == 403 and "outra página" in r.json()["detail"]
    assert cliente.get("/api/rotas").status_code == 200  # leituras não precisam


def test_post_de_outro_site_e_recusado_mesmo_com_o_cabecalho(app_local, abrir_cliente):
    cliente = abrir_cliente(app_local)
    r = cliente.post("/api/executar", json={}, headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403
    r = cliente.post("/api/executar", json={}, headers={"Origin": "null"})
    assert r.status_code == 403
    r = cliente.post("/api/executar", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = cliente.post("/api/executar", json={}, headers={"Sec-Fetch-Site": "same-site"})  # outra porta do mesmo host
    assert r.status_code == 403


def test_post_da_propria_pagina_passa(app_local, abrir_cliente, monkeypatch):
    from scanner import notificar

    monkeypatch.setattr(notificar, "enviar", lambda texto, botoes=None: None)
    cliente = abrir_cliente(app_local)
    r = cliente.post("/api/notificacao-teste", headers={"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200
    assert cliente.post("/api/notificacao-teste", headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_no_modo_rede_o_post_do_celular_passa_com_cookie_e_cabecalho(app_rede, abrir_cliente, monkeypatch):
    from scanner import notificar

    monkeypatch.setattr(notificar, "enviar", lambda texto, botoes=None: None)
    cliente = abrir_cliente(app_rede, cabecalhos={"Cookie": f"{acesso.NOME_COOKIE}={TOKEN}"}, **CELULAR)
    assert cliente.post("/api/notificacao-teste", headers={"Origin": "http://192.168.2.242:8765"}).status_code == 200
    # outro site, mesmo que o navegador mandasse o cookie, é barrado pelo Origin
    r = cliente.post("/api/notificacao-teste", headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403


# --- cabeçalhos de segurança ---------------------------------------------------------------------------------------

def test_cabecalhos_de_seguranca_em_todas_as_respostas(app_rede, abrir_cliente):
    for cliente in (abrir_cliente(app_rede), abrir_cliente(app_rede, **CELULAR)):  # com 200 e com 401
        for caminho in ("/", "/api/rotas"):
            h = cliente.get(caminho).headers
            assert h["x-content-type-options"] == "nosniff"
            assert h["x-frame-options"] == "DENY"
            assert h["referrer-policy"] == "no-referrer"
            diretivas = dict(d.strip().split(" ", 1) for d in h["content-security-policy"].split(";") if d.strip())
            assert diretivas["default-src"] == "'self'" and diretivas["frame-ancestors"] == "'none'"
            assert "script-src" not in diretivas  # script só do próprio site
            # o app.js põe style="width: ..." nos medidores, então só o estilo aceita inline
            assert "'unsafe-inline'" in diretivas["style-src"]
            assert all("'unsafe-inline'" not in v for k, v in diretivas.items() if k != "style-src")
    assert abrir_cliente(app_rede).get("/api/rotas").headers["cache-control"] == "no-store"


# --- a página e o servidor combinam ------------------------------------------------------------------------------

def test_a_pagina_manda_o_cabecalho_que_o_servidor_exige(app_local, abrir_cliente):
    """Os testes de API já mandam o cabeçalho; se o app.js deixar de mandá-lo, todo botão que grava quebra no navegador."""
    cliente = abrir_cliente(app_local)
    assert f'"{acesso.CABECALHO_CSRF}"' in cliente.get("/app.js").text
    assert 'id="quadro-acesso"' in cliente.get("/").text


# --- achados da revisão de segurança ------------------------------------------------------------------------------

def test_token_escolhido_a_mao_com_simbolos_vai_codificado_na_url(tmp_path, abrir_cliente, monkeypatch):
    """O token do .env pode ser digitado por quem usa: &, # e espaço não podem quebrar o endereço mostrado."""
    from urllib.parse import quote

    esquisito = "forte & seguro #1 com espaço, 100% ok"
    monkeypatch.setattr(acesso, "enderecos_locais", lambda: ["192.168.2.242"])
    app = web.criar_app(caminho_config=tmp_path / "c.yaml", caminho_banco=tmp_path / "p.db",
                        caminho_log=tmp_path / "l.log", consultar_tarefas=lambda: [], token=esquisito)
    url = abrir_cliente(app).get("/api/acesso").json()["enderecos"][0]["url"]
    assert url == f"http://192.168.2.242:8765/?t={quote(esquisito, safe='')}"
    # e é esse endereço, aberto como o celular abriria, que entra
    celular = abrir_cliente(app, follow_redirects=False, **CELULAR)
    assert celular.get(url.split("8765", 1)[1]).status_code == 303


def test_a_documentacao_automatica_nao_e_servida(app_local, abrir_cliente):
    """/docs e /redoc buscam script em CDN (a política de conteúdo bloqueia) e o "Try it out" não mandaria o
    cabeçalho anti-CSRF: ficariam quebrados, só aumentando a superfície."""
    cliente = abrir_cliente(app_local)
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).status_code == 404, caminho
