from datetime import date

from scanner.filtros import combinacoes, passa
from scanner.pesquisa import Voo


def voo(preco=3000, escalas=1, duracao_min=900):
    return Voo("GRU", "LIS", date(2026, 11, 10), date(2026, 11, 20), preco, "TAP", escalas, duracao_min,
               "2026-11-10 20:00", "2026-11-11 11:00", "https://exemplo")


def test_combinacoes_ida_e_volta():
    pares = combinacoes([date(2026, 11, 1), date(2026, 11, 5)], passo_dias=2, duracoes_dias=[7, 14], hoje=date(2026, 10, 1))
    assert pares == [
        (date(2026, 11, 1), date(2026, 11, 8)),
        (date(2026, 11, 1), date(2026, 11, 15)),
        (date(2026, 11, 3), date(2026, 11, 10)),
        (date(2026, 11, 3), date(2026, 11, 17)),
        (date(2026, 11, 5), date(2026, 11, 12)),
        (date(2026, 11, 5), date(2026, 11, 19)),
    ]


def test_combinacoes_so_ida_e_ignora_datas_passadas():
    pares = combinacoes([date(2026, 11, 1), date(2026, 11, 4)], hoje=date(2026, 11, 3))
    assert pares == [(date(2026, 11, 3), None), (date(2026, 11, 4), None)]


def test_exemplo_do_config_da_45_buscas():
    pares = combinacoes([date(2026, 11, 1), date(2026, 11, 30)], passo_dias=2, duracoes_dias=[7, 10, 14], hoje=date(2026, 10, 1))
    assert len(pares) == 45


def test_passa_nos_filtros():
    filtros = {"preco_max": 4500, "escalas_max": 1, "duracao_max_horas": 20}
    assert passa(voo(), filtros)
    assert passa(voo(preco=4500), filtros)
    assert not passa(voo(preco=4501), filtros)
    assert not passa(voo(escalas=2), filtros)
    assert not passa(voo(duracao_min=20 * 60 + 1), filtros)


def test_filtros_ausentes_aceitam_tudo():
    assert passa(voo(preco=99999, escalas=5, duracao_min=5000), {})


def test_combinacoes_com_lista_de_datas():
    pares = combinacoes(
        duracoes_dias=[7],
        datas=[date(2026, 9, 1), date(2026, 12, 20), [date(2026, 12, 22), date(2027, 1, 5)]],
        hoje=date(2026, 10, 1),
    )
    assert pares == [(date(2026, 12, 20), date(2026, 12, 27)), (date(2026, 12, 22), date(2027, 1, 5))]


def test_combinacoes_junta_intervalo_e_lista_sem_repetir():
    pares = combinacoes([date(2026, 11, 1), date(2026, 11, 2)], datas=[date(2026, 11, 2), date(2026, 11, 9)], hoje=date(2026, 10, 1))
    assert pares == [(date(2026, 11, 1), None), (date(2026, 11, 2), None), (date(2026, 11, 9), None)]


def test_ler_datas_do_terminal():
    from scanner.buscar import ler_data, ler_data_ou_par
    assert ler_data("22/12/2026") == date(2026, 12, 22)
    assert ler_data("2026-12-22") == date(2026, 12, 22)
    assert ler_data_ou_par("22/12/2026:29/12/2026") == [date(2026, 12, 22), date(2026, 12, 29)]
