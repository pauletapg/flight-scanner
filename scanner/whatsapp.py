"""Envio de mensagens para o seu próprio WhatsApp via CallMeBot (https://www.callmebot.com)."""

import argparse
import os

import requests
from dotenv import load_dotenv


class SemCredenciais(Exception):
    pass


def enviar(texto: str) -> None:
    telefone = os.getenv("CALLMEBOT_PHONE")
    chave = os.getenv("CALLMEBOT_APIKEY")
    if not telefone or not chave:
        raise SemCredenciais("defina CALLMEBOT_PHONE e CALLMEBOT_APIKEY no arquivo .env")

    resposta = requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": telefone, "text": texto, "apikey": chave},
        timeout=60,
    )
    resposta.raise_for_status()
    if "error" in resposta.text.lower():
        raise RuntimeError(f"CallMeBot recusou a mensagem: {resposta.text[:300]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envia uma mensagem de teste para o WhatsApp.")
    parser.add_argument("--teste", action="store_true", required=True)
    parser.parse_args()
    load_dotenv()
    enviar("✈️ Flight Scanner: mensagem de teste. Se chegou, os alertas vão funcionar.")
    print("Mensagem enviada. Confira o WhatsApp.")
