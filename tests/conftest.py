import pytest
from fastapi.testclient import TestClient

from scanner import buscar, rotas


@pytest.fixture(autouse=True)
def config_real_protegido(tmp_path, monkeypatch):
    """Nenhum teste lê ou grava o config.yaml real sem querer: o caminho padrão aponta para um arquivo inexistente."""
    inexistente = tmp_path / "sem-config" / "config.yaml"
    monkeypatch.setattr(rotas, "CAMINHO_CONFIG", inexistente)
    monkeypatch.setattr(buscar, "CAMINHO_CONFIG", inexistente)


@pytest.fixture(autouse=True)
def sem_chaves_reais(monkeypatch):
    """O fast_flights chama load_dotenv() ao ser importado, então o .env real entra no ambiente dos testes.
    Sem estas variáveis, nenhum teste envia notificação nem gasta a SerpApi de verdade; quem precisa usa setenv."""
    for nome in ("NTFY_TOPIC", "NTFY_SERVER", "CALLMEBOT_PHONE", "CALLMEBOT_APIKEY", "SERPAPI_KEY"):
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture
def abrir_cliente():
    """Cliente de teste que age como o navegador do próprio PC: IP e Host de loopback e o cabeçalho que a página
    manda em toda chamada (proteção contra CSRF). Para simular outro aparelho, passe `ip=` e `host=`."""
    def abrir(app, ip="127.0.0.1", host="127.0.0.1:8765", csrf=True, cabecalhos=None, **extra):
        enviados = ({"X-Flight-Scanner": "1"} if csrf else {}) | (cabecalhos or {})
        return TestClient(app, base_url=f"http://{host}", client=(ip, 50000), headers=enviados, **extra)

    return abrir
