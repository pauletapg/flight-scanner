"""Gera as combinações de datas de cada rota e aplica os filtros aos voos encontrados."""

from datetime import date, timedelta

from scanner.pesquisa import Voo


def combinacoes(
    ida_entre: list[date] | None = None,
    passo_dias: int = 1,
    duracoes_dias: list[int] | None = None,
    hoje: date | None = None,
    datas: list | None = None,
) -> list[tuple[date, date | None]]:
    """(ida, volta) para cada data de ida × duração. Sem durações, volta = None (só ida).

    As datas de ida vêm do intervalo `ida_entre` (de `passo_dias` em `passo_dias`) e/ou da lista
    `datas`. Cada item de `datas` é uma data de ida (combinada com as durações) ou um par
    [ida, volta] fixo. Datas de ida que já passaram são ignoradas."""
    hoje = hoje or date.today()
    idas, pares_fixos = [], []
    if ida_entre:
        inicio, fim = ida_entre
        ida = inicio
        while ida <= fim:
            idas.append(ida)
            ida += timedelta(days=passo_dias)
    for item in datas or []:
        if isinstance(item, list):
            pares_fixos.append(tuple(item))
        else:
            idas.append(item)

    pares = []
    for ida in idas:
        if duracoes_dias:
            pares += [(ida, ida + timedelta(days=d)) for d in duracoes_dias]
        else:
            pares.append((ida, None))
    pares += pares_fixos
    return [p for p in dict.fromkeys(pares) if p[0] >= hoje]


def passa(voo: Voo, filtros: dict, ignorar_preco: bool = False) -> bool:
    """O preço considerado é o menor entre o da lista do Google e o das opções de reserva."""
    preco_max = None if ignorar_preco else filtros.get("preco_max")
    escalas_max = filtros.get("escalas_max")
    duracao_max_horas = filtros.get("duracao_max_horas")
    if preco_max is not None and voo.menor_preco > preco_max:
        return False
    if escalas_max is not None and voo.escalas > escalas_max:
        return False
    if duracao_max_horas is not None and voo.duracao_min > duracao_max_horas * 60:
        return False
    return True
