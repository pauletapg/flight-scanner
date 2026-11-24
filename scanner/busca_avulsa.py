"""Busca avulsa de uma rota (todas as combinações de datas), usada pela CLI e pela interface.

O progresso sai pelo callback `progresso(i, n, texto)`: uma chamada por combinação de datas
(i de 1 a n) e, na consulta às agências (reservas), chamadas com i e n iguais a None."""

import os
import random
import time
from collections.abc import Callable
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from scanner import historico, pesquisa
from scanner.filtros import combinacoes, passa
from scanner.main import CAMINHO_BANCO, dinheiro
from scanner.pesquisa import Voo

LIMITE_SEM_CONFIRMAR = 30  # acima disso, pede confirmação para não ser bloqueado pelo Google

Progresso = Callable[[int | None, int | None, str], None]


def _nada(i: int | None, n: int | None, texto: str) -> None:
    pass


def combinacoes_da_rota(rota: dict) -> list[tuple[date, date | None]]:
    return combinacoes(rota.get("ida_entre"), rota.get("passo_dias", 1), rota.get("duracoes_dias"), datas=rota.get("datas"))


def consultar_reservas(rota: dict, voos: list[Voo], moeda: str, progresso: Progresso = _nada,
                       caminho_banco: Path = CAMINHO_BANCO) -> None:
    """Preço das agências (SerpApi) para os voos dados; grava em v.reserva_preco quando é menor."""
    if not os.getenv("SERPAPI_KEY"):
        progresso(None, None, "--reservas precisa da SERPAPI_KEY no arquivo .env.")
        return
    progresso(None, None, f"Consultando as opções de reserva de {len(voos)} voo(s) na SerpApi...")
    with closing(historico.abrir(caminho_banco)) as con:  # na interface, o servidor fica aberto: não deixa conexão para trás
        for v in voos:
            antes = pesquisa.serpapi_chamadas
            try:
                resultado = pesquisa.opcoes_reserva(v, rota["adultos"], rota["criancas"], rota["bebes_colo"], rota["classe"], moeda)
            except Exception as erro:
                progresso(None, None, f"  {v.ida:%d/%m}: falhou ({erro})")
                continue
            finally:
                historico.serpapi_somar(con, datetime.now(), pesquisa.serpapi_chamadas - antes)
            if resultado and resultado[0] < v.preco:
                v.reserva_preco, v.reserva_onde = resultado
        progresso(None, None, f"SerpApi: {historico.serpapi_usadas(con, datetime.now())} busca(s) usadas neste mês.")


def buscar(rota: dict, geral: dict, reservas: int = 0, progresso: Progresso = _nada,
           caminho_banco: Path = CAMINHO_BANCO) -> list[Voo]:
    """O melhor voo de cada combinação de datas que passou nos filtros, do mais barato ao mais caro.

    `reservas` = quantos dos mais baratos consultam o preço das agências. O preço máximo só é
    aplicado no fim, depois do preço das agências, que pode ser menor que o da lista."""
    moeda = geral.get("moeda", "BRL")
    filtros = rota.get("filtros", {})
    pares = combinacoes_da_rota(rota)
    melhores = []
    for i, (ida, volta) in enumerate(pares, 1):
        if i > 1:
            time.sleep(random.uniform(*geral.get("pausa_entre_buscas_seg", [4, 8])))
        datas = f"{ida:%d/%m} → {volta:%d/%m}" if volta else f"{ida:%d/%m} (só ida)"
        try:
            voos = pesquisa.buscar(
                rota["origem"], rota["destino"], ida, volta,
                adultos=rota["adultos"], criancas=rota["criancas"], bebes_colo=rota["bebes_colo"],
                classe=rota["classe"], moeda=moeda,
                escalas_max=filtros.get("escalas_max"), duracao_max_horas=filtros.get("duracao_max_horas"),
            )
        except pesquisa.SemConexao:
            progresso(i, len(pares), f"{datas}: sem internet; busca interrompida")
            break
        except Exception as erro:
            progresso(i, len(pares), f"{datas}: falhou ({erro})")
            continue
        aprovados = [v for v in voos if passa(v, filtros, ignorar_preco=True)]
        if aprovados:
            melhor = min(aprovados, key=lambda v: v.preco)
            melhores.append(melhor)
            progresso(i, len(pares), f"{datas}: {len(aprovados)} voo(s), melhor {dinheiro(melhor.preco, moeda)}")
        else:
            progresso(i, len(pares), f"{datas}: {len(voos)} voo(s), nenhum nos filtros")

    melhores.sort(key=lambda v: v.preco)
    if melhores and reservas:
        consultar_reservas(rota, melhores[:reservas], moeda, progresso, caminho_banco)
    return sorted((v for v in melhores if passa(v, filtros)), key=lambda v: v.menor_preco)
