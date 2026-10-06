import pytest

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
