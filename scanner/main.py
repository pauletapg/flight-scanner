"""Uma execução do Flight Scanner: busca, filtra, guarda o histórico e alerta no WhatsApp."""

import argparse
import calendar
import logging
import os
import random
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml
from dotenv import load_dotenv

from scanner import historico, notificar, pesquisa
from scanner.filtros import combinacoes, passa

PASTA = Path(__file__).resolve().parent.parent
CAMINHO_BANCO = PASTA / "data" / "precos.db"
MAX_VOOS_NA_MENSAGEM = 5
MAX_ROTAS = 3  # buscas monitoradas ao mesmo tempo
SIMBOLOS = {"BRL": "R$", "EUR": "€", "USD": "US$"}

log = logging.getLogger("scanner")


def configurar_log() -> None:
    (PASTA / "logs").mkdir(exist_ok=True)
    handlers = [RotatingFileHandler(PASTA / "logs" / "scanner.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr:  # na tarefa agendada (pythonw) não há console
        handlers.append(logging.StreamHandler())
    # As bibliotecas só registram avisos; o scanner registra também as informações de cada busca.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    log.setLevel(logging.INFO)


def dinheiro(valor: int, moeda: str) -> str:
    return f"{SIMBOLOS.get(moeda, moeda)} {valor:,}".replace(",", ".")


def formatar_alerta(alertas: list, moeda: str) -> str:
    alertas = sorted(alertas, key=lambda a: a[1].menor_preco)
    linhas = [f"✈️ Flight Scanner: {len(alertas)} alerta(s)"]
    for rota, voo, (motivo, minimo) in alertas[:MAX_VOOS_NA_MENSAGEM]:
        if voo.volta:
            datas = f"{voo.ida:%d/%m} → {voo.volta:%d/%m} ({(voo.volta - voo.ida).days} dias)"
        else:
            datas = f"{voo.ida:%d/%m} (só ida)"
        escalas = "direto" if voo.escalas == 0 else f"{voo.escalas} escala(s)"
        duracao = f"{voo.duracao_min // 60}h{voo.duracao_min % 60:02d}"
        if motivo == "novo":
            porque = "Novo voo dentro dos filtros"
        else:
            porque = f"Caiu {round((1 - voo.preco / minimo) * 100)}% (mínimo anterior {dinheiro(minimo, moeda)})"
        linhas += [
            "",
            f"*{rota}*",
            f"{voo.origem}→{voo.destino} {datas}",
            f"{dinheiro(voo.preco, moeda)} · {escalas} · {duracao} · {voo.companhias}",
        ]
        if voo.reserva_preco:
            linhas.append(f"*{dinheiro(voo.reserva_preco, moeda)} em {voo.reserva_onde}*")
        linhas += [porque, voo.link]
    if len(alertas) > MAX_VOOS_NA_MENSAGEM:
        linhas += ["", f"+ {len(alertas) - MAX_VOOS_NA_MENSAGEM} outro(s) alerta(s)"]
    return "\n".join(linhas)


def botoes_alerta(alertas: list, moeda: str) -> list[tuple[str, str]]:
    """Botões da notificação: um para cada um dos 3 voos mais baratos, abrindo o Google Flights."""
    botoes = []
    for _, voo, _ in sorted(alertas, key=lambda a: a[1].menor_preco)[:3]:
        datas = f"{voo.ida:%d/%m}→{voo.volta:%d/%m}" if voo.volta else f"{voo.ida:%d/%m}"
        botoes.append((f"{dinheiro(voo.menor_preco, moeda)} {datas}", voo.link))
    return botoes


def saldo_serpapi(con, geral: dict) -> int:
    """Consultas da SerpApi que ainda podem ser feitas hoje, dividindo o que sobra do mês
    igualmente pelos dias que faltam. Zero se não houver SERPAPI_KEY."""
    if not os.getenv("SERPAPI_KEY"):
        return 0
    agora = datetime.now()
    limite = geral.get("serpapi", {}).get("limite_mensal", 240)
    no_mes = historico.serpapi_usadas(con, agora)
    hoje = historico.serpapi_usadas(con, agora, no_dia=True)
    dias_que_faltam = calendar.monthrange(agora.year, agora.month)[1] - agora.day + 1
    cota_hoje = (limite - (no_mes - hoje)) // dias_que_faltam
    return max(0, min(limite - no_mes, cota_hoje - hoje))


def consultar_reservas(con, geral: dict, resultados: list, moeda: str) -> None:
    """Para os voos mais baratos perto do teto, busca o preço nas "Opções de reserva" (agências
    costumam ser ~10% mais baratas que a companhia). Usa o cache quando o preço da lista não mudou."""
    config_serp = geral.get("serpapi", {})
    margem = config_serp.get("margem_percentual", 15)
    candidatos = []
    for rota, ida, volta, voos in resultados:
        teto = rota.get("filtros", {}).get("preco_max")
        elegiveis = [v for v in voos if passa(v, rota.get("filtros", {}), ignorar_preco=True)]
        if teto is None or not elegiveis:
            continue
        voo = min(elegiveis, key=lambda v: v.preco)
        if voo.preco <= teto * (1 + margem / 100):
            candidatos.append((rota, voo))

    consultas = config_serp.get("consultas_reserva_por_execucao", 1)
    for rota, voo in sorted(candidatos, key=lambda c: c[1].preco):
        cache = historico.reserva_em_cache(con, rota["nome"], voo)
        if cache is None:
            if consultas <= 0 or saldo_serpapi(con, geral) < (3 if voo.volta else 2):
                continue
            consultas -= 1
            antes = pesquisa.serpapi_chamadas
            try:
                resultado = pesquisa.opcoes_reserva(
                    voo, rota.get("adultos", 1), rota.get("criancas", 0), rota.get("bebes_colo", 0),
                    rota.get("classe", "economy"), moeda,
                )
            except Exception:
                log.exception("Falha ao consultar as opções de reserva na SerpApi")
                continue
            finally:
                historico.serpapi_somar(con, datetime.now(), pesquisa.serpapi_chamadas - antes)
            historico.salvar_reserva(con, rota["nome"], voo, resultado, datetime.now())
            cache = resultado or (None, "")
            log.info("Opções de reserva %s %s → %s: %s", rota["nome"], voo.ida, voo.volta or "só ida",
                     f"{dinheiro(cache[0], moeda)} em {cache[1]}" if cache[0] else "nenhuma com preço")
        preco, onde = cache
        if preco and preco < voo.preco:
            voo.reserva_preco, voo.reserva_onde = preco, onde


def executar(config: dict, nome_rota: str | None = None, dry_run: bool = False) -> None:
    geral = config["geral"]
    moeda = geral.get("moeda", "BRL")
    ativas = [r for r in config["rotas"] if not r.get("pausada")]
    if len(ativas) > MAX_ROTAS:
        log.error("O config.yaml tem %d rotas ativas; o máximo é %d. Pause ou apague as que sobram.", len(ativas), MAX_ROTAS)
        raise SystemExit(f"Máximo de {MAX_ROTAS} rotas ativas no config.yaml")
    rotas = [r for r in ativas if nome_rota in (None, r["nome"])]
    if not rotas:
        raise SystemExit(f"Rota não encontrada no config.yaml: {nome_rota!r}")

    todas = [
        (rota, ida, volta)
        for rota in rotas
        for ida, volta in combinacoes(
            rota.get("ida_entre"), rota.get("passo_dias", 1), rota.get("duracoes_dias"), datas=rota.get("datas"),
        )
    ]
    con = historico.abrir(CAMINHO_BANCO)
    lote = historico.proximo_lote(con, f"cursor:{nome_rota or '*'}", todas, geral.get("max_buscas_por_execucao", 10))
    log.info("Início: %d de %d combinações de datas", len(lote), len(todas))

    resultados = []
    for i, (rota, ida, volta) in enumerate(lote):
        if i:
            time.sleep(random.uniform(*geral.get("pausa_entre_buscas_seg", [4, 8])))
        filtros = rota.get("filtros", {})
        antes = pesquisa.serpapi_chamadas
        try:
            voos = pesquisa.buscar(
                rota["origem"], rota["destino"], ida, volta,
                adultos=rota.get("adultos", 1),
                criancas=rota.get("criancas", 0),
                bebes_colo=rota.get("bebes_colo", 0),
                classe=rota.get("classe", "economy"),
                moeda=moeda,
                escalas_max=filtros.get("escalas_max"),
                duracao_max_horas=filtros.get("duracao_max_horas"),
                usar_serpapi=saldo_serpapi(con, geral) > 0,
            )
        except Exception:
            log.exception("Falha na busca %s %s → %s", rota["nome"], ida, volta or "só ida")
            continue
        finally:
            historico.serpapi_somar(con, datetime.now(), pesquisa.serpapi_chamadas - antes)
        resultados.append((rota, ida, volta, voos))

    consultar_reservas(con, geral, resultados, moeda)

    alertas = []
    for rota, ida, volta, voos in resultados:
        filtros = rota.get("filtros", {})
        avaliados = [(v, passa(v, filtros)) for v in voos]
        aprovados = [v for v, ok in avaliados if ok]
        melhor = min(aprovados, key=lambda v: v.menor_preco) if aprovados else None
        log.info(
            "%s %s → %s: %d voos, %d nos filtros%s",
            rota["nome"], ida, volta or "só ida", len(voos), len(aprovados),
            f", melhor {dinheiro(melhor.menor_preco, moeda)}" if melhor else "",
        )
        if melhor:
            motivo = historico.deve_alertar(con, rota["nome"], melhor, rota.get("alerta", {}).get("queda_percentual", 10))
            if motivo:
                alertas.append((rota["nome"], melhor, motivo))
        historico.salvar(con, rota["nome"], avaliados, moeda, datetime.now())

    if not alertas:
        log.info("Fim: nenhum alerta")
        return

    # Uma notificação por rota, para cada busca (até 3) chegar separada no celular.
    enviados = 0
    for nome in dict.fromkeys(a[0] for a in alertas):
        da_rota = [a for a in alertas if a[0] == nome]
        mensagem = formatar_alerta(da_rota, moeda)
        if dry_run:
            print("\n" + mensagem + "\n")
            continue
        try:
            notificar.enviar(mensagem, botoes_alerta(da_rota, moeda))
        except notificar.SemCredenciais as erro:
            log.warning("Notificação não configurada (%s). Alerta não enviado:\n%s", erro, mensagem)
            return
        except Exception:
            log.exception("Falha ao enviar a notificação de %s; esses voos serão avaliados de novo na próxima busca das mesmas datas", nome)
            continue
        agora = datetime.now()
        for rota, voo, _ in da_rota:
            historico.registrar_alerta(con, rota, voo, agora)
        enviados += len(da_rota)
    if dry_run:
        log.info("Fim: %d alerta(s) (dry-run, não enviado)", len(alertas))
    else:
        log.info("Fim: %d alerta(s) enviado(s)", enviados)


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca voos, guarda o histórico e alerta no celular.")
    parser.add_argument("--dry-run", action="store_true", help="mostra o alerta no terminal em vez de enviar")
    parser.add_argument("--rota", help="busca só a rota com este nome (padrão: todas)")
    args = parser.parse_args()
    load_dotenv(PASTA / ".env")
    configurar_log()
    config = yaml.safe_load((PASTA / "config.yaml").read_text(encoding="utf-8"))
    try:
        executar(config, args.rota, args.dry_run)
    except SystemExit:
        raise
    except Exception:
        log.exception("Erro inesperado na execução")
        raise


if __name__ == "__main__":
    main()
