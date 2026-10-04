"""Busca de voos: Google Flights via fast-flights, com reserva opcional na SerpApi."""

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime

import json

import requests
from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query
from fast_flights.fetcher import fetch_flights_html
from fast_flights.parser import parse_js
from selectolax.lexbor import LexborHTMLParser

log = logging.getLogger(__name__)


@dataclass
class Voo:
    origem: str
    destino: str
    ida: date
    volta: date | None
    preco: int
    companhias: str
    escalas: int
    duracao_min: int  # do trecho de ida, incluindo as escalas
    partida: str  # "AAAA-MM-DD HH:MM", hora local
    chegada: str
    link: str
    reserva_preco: int | None = None  # menor preço nas "Opções de reserva" (agências), via SerpApi
    reserva_onde: str = ""

    @property
    def menor_preco(self) -> int:
        return min(self.preco, self.reserva_preco or self.preco)


def buscar(
    origem: str,
    destino: str,
    ida: date,
    volta: date | None,
    adultos: int = 1,
    criancas: int = 0,
    bebes_colo: int = 0,
    classe: str = "economy",
    moeda: str = "BRL",
    escalas_max: int | None = None,
    duracao_max_horas: float | None = None,
    usar_serpapi: bool = True,
) -> list[Voo]:
    """Busca no Google Flights; se falhar e houver SERPAPI_KEY (e saldo), tenta a SerpApi."""
    try:
        return _buscar_google(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda, escalas_max, duracao_max_horas)
    except Exception as erro:
        if not (os.getenv("SERPAPI_KEY") and usar_serpapi):
            raise
        log.warning("Google Flights falhou (%r); tentando a SerpApi", erro)
        return _buscar_serpapi(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda, escalas_max)


def _buscar_google(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda, escalas_max, duracao_max_horas):
    duracao_max = int(duracao_max_horas * 60) if duracao_max_horas else None
    trechos = [FlightQuery(date=ida.isoformat(), from_airport=origem, to_airport=destino, max_duration_minutes=duracao_max)]
    if volta:
        trechos.append(FlightQuery(date=volta.isoformat(), from_airport=destino, to_airport=origem, max_duration_minutes=duracao_max))

    consulta = create_query(
        flights=trechos,
        trip="round-trip" if volta else "one-way",
        seat=classe,
        passengers=Passengers(adults=adultos, children=criancas, infants_on_lap=bebes_colo),
        language="pt-BR",
        currency=moeda,
        max_stops=escalas_max,
    )
    try:
        resultados = _todos_os_voos(fetch_flights_html(consulta))
    except FlightsNotFound:
        return []

    voos = []
    for r in resultados:
        pernas = r.flights
        horarios = [(_data_hora(p.departure), _data_hora(p.arrival)) for p in pernas]
        conexoes = sum(
            (proxima[0] - anterior[1]).total_seconds() // 60
            for anterior, proxima in zip(horarios, horarios[1:])
        )
        voos.append(Voo(
            origem=origem,
            destino=destino,
            ida=ida,
            volta=volta,
            preco=int(r.price),
            companhias=", ".join(r.airlines),
            escalas=len(pernas) - 1,
            duracao_min=int(sum(p.duration for p in pernas) + conexoes),
            partida=f"{horarios[0][0]:%Y-%m-%d %H:%M}",
            chegada=f"{horarios[-1][1]:%Y-%m-%d %H:%M}",
            link=consulta.url(),
        ))
    return voos


def _todos_os_voos(html: str) -> list:
    """O Google manda duas listas: "Principais voos" (payload[2], onde costumam estar os mais
    baratos) e "Outros voos" (payload[3]). O parser do fast-flights 3.1.0 só lê a segunda,
    então passamos cada lista para ele separadamente."""
    js = LexborHTMLParser(html).css_first(r"script.ds\:1").text()
    dados = js.split("data:", 1)[1].rsplit(",", 1)[0]
    if dados.endswith("errorHasStatus: true"):
        raise FlightsNotFound("no flights found; received error")
    payload = json.loads(dados)
    voos = []
    for secao in (2, 3):
        if payload[secao] and payload[secao][0]:
            copia = list(payload)
            copia[3] = payload[secao]
            voos += parse_js("data:" + json.dumps(copia) + ",x")
    return voos


def _data_hora(d) -> datetime:
    return datetime(*d.date, *d.time)


_CLASSES_SERPAPI = {"economy": 1, "premium-economy": 2, "business": 3, "first": 4}
# A SerpApi não aceita códigos IATA de cidade. Para o Rio usamos o ID da cidade no Google
# (/m/06gmr): pesquisando pela cidade, o Google mostra mais agências nas opções de reserva
# (a Zupper só apareceu assim). Para as outras cidades, a lista de aeroportos.
_CIDADES = {"RIO": "/m/06gmr", "SAO": "GRU,CGH,VCP", "BHZ": "CNF,PLU"}

serpapi_chamadas = 0  # consultas feitas nesta execução (cada uma gasta 1 do plano)


def _serpapi(params: dict) -> dict:
    global serpapi_chamadas
    serpapi_chamadas += 1
    params = {"engine": "google_flights", "gl": "br", "hl": "pt", "api_key": os.environ["SERPAPI_KEY"], **params}
    resposta = requests.get("https://serpapi.com/search.json", params=params, timeout=90)
    resposta.raise_for_status()
    dados = resposta.json()
    if "error" in dados:
        raise RuntimeError(f"SerpApi: {dados['error']}")
    return dados


def _params_serpapi(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda) -> dict:
    params = {
        "departure_id": _CIDADES.get(origem, origem),
        "arrival_id": _CIDADES.get(destino, destino),
        "outbound_date": ida.isoformat(),
        "type": 1 if volta else 2,
        "currency": moeda,
        "adults": adultos,
        "children": criancas,
        "infants_on_lap": bebes_colo,
        "travel_class": _CLASSES_SERPAPI[classe],
    }
    if volta:
        params["return_date"] = volta.isoformat()
    return params


def _buscar_serpapi(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda, escalas_max):
    params = _params_serpapi(origem, destino, ida, volta, adultos, criancas, bebes_colo, classe, moeda)
    params["stops"] = {0: 1, 1: 2, 2: 3}.get(escalas_max, 0)  # 1 = sem escalas, 2 = até 1, 3 = até 2, 0 = qualquer
    dados = _serpapi(params)
    link = dados.get("search_metadata", {}).get("google_flights_url", "")

    voos = []
    for opcao in dados.get("best_flights", []) + dados.get("other_flights", []):
        if "price" not in opcao:
            continue
        pernas = opcao["flights"]
        voos.append(Voo(
            origem=origem,
            destino=destino,
            ida=ida,
            volta=volta,
            preco=int(opcao["price"]),
            companhias=", ".join(dict.fromkeys(p["airline"] for p in pernas)),
            escalas=len(pernas) - 1,
            duracao_min=int(opcao["total_duration"]),
            partida=pernas[0]["departure_airport"]["time"],
            chegada=pernas[-1]["arrival_airport"]["time"],
            link=link,
        ))
    return voos


def opcoes_reserva(voo: Voo, adultos=1, criancas=0, bebes_colo=0, classe="economy", moeda="BRL") -> tuple[int, str] | None:
    """Menor preço nas "Opções de reserva" do Google (companhia ou agências como Zupper) para este
    voo de ida, com a volta mais barata. Gasta 3 consultas da SerpApi (2 se for só ida).
    Devolve (preço, onde comprar) ou None se não achar o voo."""
    params = _params_serpapi(voo.origem, voo.destino, voo.ida, voo.volta, adultos, criancas, bebes_colo, classe, moeda)
    params["deep_search"] = "true"

    def escolher(dados, igual_ao_voo):
        opcoes = [o for o in dados.get("best_flights", []) + dados.get("other_flights", []) if "price" in o]
        if igual_ao_voo:
            opcoes = [o for o in opcoes if o["flights"][0]["departure_airport"]["time"] == voo.partida
                      and len(o["flights"]) - 1 == voo.escalas]
        return min(opcoes, key=lambda o: o["price"]) if opcoes else None

    ida = escolher(_serpapi(params), igual_ao_voo=True)
    if not ida:
        log.warning("SerpApi não encontrou o voo de ida %s %s %s", voo.origem, voo.destino, voo.partida)
        return None
    token = ida.get("booking_token")
    if voo.volta:
        volta = escolher(_serpapi({**params, "departure_token": ida["departure_token"]}), igual_ao_voo=False)
        if not volta:
            return None
        token = volta["booking_token"]

    dados = _serpapi({**params, "booking_token": token})
    precos = []
    for opcao in dados.get("booking_options", []):
        if "together" in opcao and opcao["together"].get("price"):
            precos.append((int(opcao["together"]["price"]), opcao["together"].get("book_with", "?")))
        elif opcao.get("separate_tickets") and opcao.get("departing", {}).get("price") and opcao.get("returning", {}).get("price"):
            ida_, volta_ = opcao["departing"], opcao["returning"]
            precos.append((int(ida_["price"]) + int(volta_["price"]), f"{ida_.get('book_with', '?')} + {volta_.get('book_with', '?')}"))
    return min(precos) if precos else None
