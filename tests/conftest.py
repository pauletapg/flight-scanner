import pytest

from scanner import buscar, rotas


@pytest.fixture(autouse=True)
def config_real_protegido(tmp_path, monkeypatch):
    """Nenhum teste lê ou grava o config.yaml real sem querer: o caminho padrão aponta para um arquivo inexistente."""
    inexistente = tmp_path / "sem-config" / "config.yaml"
    monkeypatch.setattr(rotas, "CAMINHO_CONFIG", inexistente)
    monkeypatch.setattr(buscar, "CAMINHO_CONFIG", inexistente)
