"""Envia os alertas: pelo ntfy (notificação no celular) se NTFY_TOPIC estiver no .env,
senão pelo WhatsApp via CallMeBot."""

import argparse
import os

import requests
from dotenv import load_dotenv

from scanner import whatsapp


class SemCredenciais(Exception):
    pass


def enviar(texto: str, botoes: list[tuple[str, str]] | None = None) -> None:
    """`texto` começa com uma linha de título; `botoes` são (rótulo, link), no máximo 3."""
    if os.getenv("NTFY_TOPIC"):
        _enviar_ntfy(texto, botoes or [])
    elif os.getenv("CALLMEBOT_PHONE") and os.getenv("CALLMEBOT_APIKEY"):
        whatsapp.enviar(texto)
    else:
        raise SemCredenciais("defina NTFY_TOPIC (ou CALLMEBOT_PHONE e CALLMEBOT_APIKEY) no arquivo .env")


def _enviar_ntfy(texto: str, botoes: list[tuple[str, str]]) -> None:
    titulo, _, corpo = texto.replace("*", "").partition("\n")  # * é negrito só no WhatsApp
    dados = {
        "topic": os.environ["NTFY_TOPIC"],
        "title": titulo.strip(),
        "message": corpo.strip() or titulo.strip(),
        "tags": ["airplane"],
        "priority": 4,  # alta: toca e aparece por cima no celular
    }
    if botoes:
        dados["click"] = botoes[0][1]  # tocar na notificação abre o voo mais barato
        dados["actions"] = [{"action": "view", "label": rotulo, "url": link} for rotulo, link in botoes[:3]]
    # Publicar em JSON (na raiz do servidor) aceita acentos e emojis no título, o que os cabeçalhos HTTP não aceitam.
    servidor = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    resposta = requests.post(servidor, json=dados, timeout=60)
    resposta.raise_for_status()


def enviar_teste() -> None:
    enviar(
        "✈️ Flight Scanner: teste\nSe esta notificação chegou, os alertas vão funcionar.",
        [("Abrir o Google Flights", "https://www.google.com/travel/flights?hl=pt-BR")],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envia uma notificação de teste.")
    parser.add_argument("--teste", action="store_true", required=True)
    parser.parse_args()
    load_dotenv()
    enviar_teste()
    print("Notificação enviada. Confira o celular.")
