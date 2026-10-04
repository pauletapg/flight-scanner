from datetime import date

from scanner import main, notificar
from scanner.pesquisa import Voo


def test_ntfy_separa_titulo_tira_negrito_e_monta_botoes(monkeypatch):
    enviados = []

    class Resposta:
        def raise_for_status(self):
            pass

    monkeypatch.setenv("NTFY_TOPIC", "voo-teste")
    monkeypatch.setattr(notificar.requests, "post", lambda url, json, timeout: enviados.append((url, json)) or Resposta())

    v1 = Voo("RIO", "REC", date(2026, 12, 21), date(2026, 12, 27), 1855, "Gol", 0, 165, "2026-12-21 14:50", "", "https://um")
    v1.reserva_preco, v1.reserva_onde = 1635, "LATAM, Gol"
    v2 = Voo("RIO", "REC", date(2026, 12, 23), date(2026, 12, 30), 1855, "Gol", 0, 170, "2026-12-23 21:25", "", "https://dois")
    alertas = [("Rio → Recife", v2, ("novo", None)), ("Rio → Recife", v1, ("novo", None))]
    notificar.enviar(main.formatar_alerta(alertas, "BRL"), main.botoes_alerta(alertas, "BRL"))

    url, dados = enviados[0]
    assert url == "https://ntfy.sh"
    assert dados["topic"] == "voo-teste"
    assert dados["title"] == "✈️ Flight Scanner: 2 alerta(s)"
    assert "*" not in dados["message"]
    assert "R$ 1.635 em LATAM, Gol" in dados["message"]
    assert dados["click"] == "https://um"
    assert dados["actions"][0] == {"action": "view", "label": "R$ 1.635 21/12→27/12", "url": "https://um"}
    assert len(dados["actions"]) == 2


def test_sem_configuracao_avisa(monkeypatch):
    for nome in ("NTFY_TOPIC", "CALLMEBOT_PHONE", "CALLMEBOT_APIKEY"):
        monkeypatch.delenv(nome, raising=False)
    try:
        notificar.enviar("x")
    except notificar.SemCredenciais:
        pass
    else:
        raise AssertionError("deveria avisar que falta configuração")
