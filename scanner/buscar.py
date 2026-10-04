"""Busca avulsa pelo terminal: escolhe origem, destino, datas, passageiros e filtros na hora,
mostra os melhores voos com o link e, com --salvar, passa a monitorar a rota no config.yaml.

Exemplo:
    python -m scanner.buscar --origem RIO --destino REC --ida-entre 20/12/2026 23/12/2026 \\
        --duracoes 6 7 --adultos 2 --duracao-max 6
"""

import argparse
import random
import sys
import time
from datetime import date, datetime

import os

import yaml
from dotenv import load_dotenv

from scanner import historico, pesquisa
from scanner.filtros import combinacoes, passa
from scanner.main import CAMINHO_BANCO, MAX_ROTAS, PASTA, dinheiro

EXEMPLO = r"""FLIGHT SCANNER: comandos principais (abra o "Fast scanner.cmd" e digite os comandos)

1) BUSCAR AGORA e, se quiser, passar a monitorar a cada 2 h:

  .\buscar --origem RIO --destino REC `
      --ida-entre 20/12/2026 23/12/2026 --duracoes 6 7 8 `
      --adultos 2 --criancas 1 --escalas-max 1 --duracao-max 6 --preco-max 5000 --salvar

  --origem / --destino   aeroporto ou cidade (RIO, GIG, SDU, GRU, SAO, REC...)
  --ida-entre A B        a ida pode ser em qualquer dia de A até B (aqui: 20, 21, 22 e 23/12)
  --datas D1 D2 ...      datas de ida avulsas, ou pares ida:volta fixos (ex.: 22/12:29/12)
  --duracoes 6 7 8       QUANTOS DIAS DURA A VIAGEM: a volta é 6, 7 ou 8 dias depois da ida.
                         Cada dia de ida é combinado com cada duração (4 idas x 3 durações = 12 buscas).
                         Sem --duracoes, busca só ida.
  --adultos / --criancas / --bebes   passageiros (criança = 2 a 11 anos, bebê = menor de 2, no colo)
  --classe               economy (padrão), premium-economy, business, first
  --escalas-max 1        no máximo 1 escala
  --duracao-max 6        no máximo 6 horas de voo em cada sentido, contando as escalas
  --preco-max 5000       preço TOTAL da viagem, somando todos os passageiros
  --reservas N           consulta o preço das agências para os N mais baratos (gasta a cota da SerpApi)
  --top N                quantos resultados mostrar (padrão 10)
  --salvar               monitora essa busca a cada 2 h e avisa no celular (máx. %d buscas ativas;
                         com todas as vagas ocupadas, pergunta qual substituir)
  --nome "..."           nome da busca ao salvar    --queda 10   alerta se o preço cair 10%%

2) GERENCIAR AS BUSCAS SALVAS:

  .\buscar --listar                 mostra as buscas, o estado e as vagas usadas
  .\buscar --pausar  "NOME"         para a busca sem apagar (não gasta pesquisas, libera a vaga)
  .\buscar --retomar "NOME"         reativa uma busca pausada
  .\buscar --remover "NOME"         apaga a busca

3) OUTROS COMANDOS:

  scanner --dry-run   roda o scanner agora, mostrando os alertas sem enviar
  relatorio           relatório do histórico de preços
  (notificação de teste: .\.venv\Scripts\python.exe -m scanner.notificar --teste)

Todas as opções: .\buscar --help
""" % MAX_ROTAS

CAMINHO_CONFIG = PASTA / "config.yaml"
LIMITE_SEM_CONFIRMAR = 30  # acima disso, pede --forcar para não ser bloqueado pelo Google


def ler_data(texto: str) -> date:
    """Aceita 22/12/2026, 22/12 (ano atual ou o próximo, se já passou) ou 2026-12-22."""
    texto = texto.strip()
    try:
        if "/" not in texto:
            return date.fromisoformat(texto)
        partes = [int(p) for p in texto.split("/")]
        if len(partes) == 3:
            return date(partes[2], partes[1], partes[0])
        hoje = date.today()
        d = date(hoje.year, partes[1], partes[0])
        return d if d >= hoje else date(hoje.year + 1, partes[1], partes[0])
    except ValueError:
        raise argparse.ArgumentTypeError(f"data inválida: {texto!r} (use 22/12/2026 ou 2026-12-22)")


def ler_data_ou_par(texto: str) -> date | list[date]:
    """22/12/2026 = data de ida; 22/12/2026:29/12/2026 = ida e volta fixas."""
    if ":" in texto:
        ida, volta = texto.split(":", 1)
        return [ler_data(ida), ler_data(volta)]
    return ler_data(texto)


def montar_rota(args: argparse.Namespace) -> dict:
    rota = {
        "nome": args.nome or f"{args.origem} → {args.destino}",
        "origem": args.origem.upper(),
        "destino": args.destino.upper(),
    }
    if args.ida_entre:
        rota["ida_entre"] = args.ida_entre
        rota["passo_dias"] = args.passo
    if args.datas:
        rota["datas"] = args.datas
    if args.duracoes:
        rota["duracoes_dias"] = args.duracoes
    rota |= {"adultos": args.adultos, "criancas": args.criancas, "bebes_colo": args.bebes, "classe": args.classe}
    filtros = {"preco_max": args.preco_max, "escalas_max": args.escalas_max, "duracao_max_horas": args.duracao_max}
    rota["filtros"] = {k: v for k, v in filtros.items() if v is not None}
    rota["alerta"] = {"queda_percentual": args.queda}
    return rota


def _blocos(texto: str) -> tuple[str, list[str]]:
    """Separa o config.yaml em (cabeçalho até 'rotas:', um texto por rota), preservando os comentários."""
    linhas = texto.splitlines(keepends=True)
    inicio = next(i for i, l in enumerate(linhas) if l.startswith("rotas:")) + 1
    blocos: list[str] = []
    for linha in linhas[inicio:]:
        if linha.startswith("  - "):
            blocos.append(linha)
        elif blocos:
            blocos[-1] += linha
    return "".join(linhas[:inicio]), blocos


def _montar(cabecalho: str, blocos: list[str]) -> str:
    return cabecalho + "".join("\n" + b.strip("\n") + "\n" for b in blocos)


def _ativas(rotas: list[dict]) -> list[dict]:
    return [r for r in rotas if not r.get("pausada")]


def _escolher(perguntas: str, nomes: list[str]) -> int | None:
    for n, nome in enumerate(nomes, 1):
        print(f"  {n}) {nome}")
    resp = input(perguntas).strip()
    return int(resp) - 1 if resp.isdigit() and 1 <= int(resp) <= len(nomes) else None


def salvar_no_config(rota: dict) -> None:
    """Acrescenta a rota no config.yaml, mantendo os comentários. Com 3 buscas ativas, pergunta qual substituir."""
    original = CAMINHO_CONFIG.read_text(encoding="utf-8")
    existentes = yaml.safe_load(original)["rotas"] or []
    if any(r["nome"] == rota["nome"] for r in existentes):
        raise SystemExit(f"Já existe uma rota chamada {rota['nome']!r} no config.yaml. Escolha outro --nome.")
    cabecalho, blocos = _blocos(original)
    if len(_ativas(existentes)) >= MAX_ROTAS:
        print(f"\nJá há {MAX_ROTAS} buscas monitoradas (o máximo):")
        if not sys.stdin.isatty():
            raise SystemExit("Sem terminal para perguntar; pause ou remova uma busca antes (--pausar / --remover).")
        if input("Quer substituir uma delas pela nova? [s/N] ").strip().lower() not in ("s", "sim"):
            raise SystemExit("Busca nova não salva.")
        ativas = [r["nome"] for r in _ativas(existentes)]
        escolha = _escolher("Substituir qual? (número, Enter cancela) ", ativas)
        if escolha is None:
            raise SystemExit("Busca nova não salva.")
        indice = next(i for i, r in enumerate(existentes) if r["nome"] == ativas[escolha])
        print(f"Substituindo {ativas[escolha]!r}.")
        del blocos[indice]
    bloco = yaml.safe_dump([rota], allow_unicode=True, sort_keys=False, default_flow_style=None)
    blocos.append("".join("  " + linha for linha in bloco.splitlines(keepends=True)))
    novo = _montar(cabecalho, blocos)
    yaml.safe_load(novo)  # garante que o arquivo continua válido antes de gravar
    CAMINHO_CONFIG.write_text(novo, encoding="utf-8")


def gerenciar(acao: str, nome: str | None) -> None:
    """--listar, --pausar, --retomar e --remover, sem precisar editar o config.yaml na mão."""
    original = CAMINHO_CONFIG.read_text(encoding="utf-8")
    rotas = yaml.safe_load(original)["rotas"] or []
    if acao == "listar":
        if not rotas:
            print("Nenhuma busca salva.")
        for r in rotas:
            estado = "PAUSADA" if r.get("pausada") else "ativa"
            print(f"[{estado}] {r['nome']}: {r['origem']} → {r['destino']}, "
                  f"{r.get('adultos', 1)} adulto(s), {r.get('criancas', 0)} criança(s), teto {r.get('filtros', {}).get('preco_max', '-')}")
        print(f"\n{len(_ativas(rotas))} de {MAX_ROTAS} vagas ativas usadas.")
        return
    indices = [i for i, r in enumerate(rotas) if r["nome"] == nome]
    if not indices:
        nomes = "\n".join(f"  - {r['nome']}" for r in rotas)
        raise SystemExit(f"Não achei a busca {nome!r}. As salvas são:\n{nomes}")
    i = indices[0]
    cabecalho, blocos = _blocos(original)
    if acao == "remover":
        del blocos[i]
    else:
        linhas = [l for l in blocos[i].splitlines(keepends=True) if not l.strip().startswith("pausada:")]
        if acao == "pausar":
            linhas.insert(1, "    pausada: true\n")
        blocos[i] = "".join(linhas)
    novo = _montar(cabecalho, blocos)
    yaml.safe_load(novo)
    CAMINHO_CONFIG.write_text(novo, encoding="utf-8")
    print({"remover": "Removida", "pausar": "Pausada (não gasta buscas)", "retomar": "Retomada"}[acao] + f": {nome}")
    if acao == "retomar" and len(_ativas(yaml.safe_load(novo)["rotas"])) > MAX_ROTAS:
        print(f"Atenção: agora há mais de {MAX_ROTAS} buscas ativas; pause ou remova outra, senão o scanner não roda.")


def consultar_reservas(rota: dict, voos: list, moeda: str) -> None:
    if not os.getenv("SERPAPI_KEY"):
        print("\n--reservas precisa da SERPAPI_KEY no arquivo .env.")
        return
    con = historico.abrir(CAMINHO_BANCO)
    print(f"\nConsultando as opções de reserva de {len(voos)} voo(s) na SerpApi...")
    for v in voos:
        antes = pesquisa.serpapi_chamadas
        try:
            resultado = pesquisa.opcoes_reserva(v, rota["adultos"], rota["criancas"], rota["bebes_colo"], rota["classe"], moeda)
        except Exception as erro:
            print(f"  {v.ida:%d/%m}: falhou ({erro})")
            continue
        finally:
            historico.serpapi_somar(con, datetime.now(), pesquisa.serpapi_chamadas - antes)
        if resultado and resultado[0] < v.preco:
            v.reserva_preco, v.reserva_onde = resultado
    print(f"SerpApi: {historico.serpapi_usadas(con, datetime.now())} busca(s) usadas neste mês.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 1:
        print(EXEMPLO)
        return
    p = argparse.ArgumentParser(
        description="Busca voos agora, com os parâmetros escolhidos no terminal.",
        epilog="Datas aceitam 22/12/2026, 22/12 ou 2026-12-22.",
    )
    p.add_argument("--origem", help="código do aeroporto ou cidade (ex.: RIO, GIG, GRU, SAO)")
    p.add_argument("--destino", help="código do aeroporto ou cidade (ex.: REC)")
    g = p.add_argument_group("datas (use --ida-entre, --datas ou os dois)")
    g.add_argument("--ida-entre", nargs=2, type=ler_data, metavar=("INICIO", "FIM"), help="intervalo de datas de ida")
    g.add_argument("--passo", type=int, default=1, help="testa a ida de N em N dias dentro do intervalo (padrão 1)")
    g.add_argument("--datas", nargs="+", type=ler_data_ou_par, metavar="DATA",
                   help="datas de ida avulsas, ou pares ida:volta fixos (ex.: 22/12:29/12)")
    g.add_argument("--duracoes", nargs="+", type=int, metavar="DIAS",
                   help="dias de viagem para cada data de ida (sem isso, busca só ida)")
    g = p.add_argument_group("passageiros")
    g.add_argument("--adultos", type=int, default=1)
    g.add_argument("--criancas", type=int, default=0, help="2 a 11 anos")
    g.add_argument("--bebes", type=int, default=0, help="menores de 2 anos, no colo")
    g.add_argument("--classe", default="economy", choices=["economy", "premium-economy", "business", "first"])
    g = p.add_argument_group("filtros")
    g.add_argument("--preco-max", type=int, help="preço TOTAL da viagem, somando todos os passageiros")
    g.add_argument("--escalas-max", type=int)
    g.add_argument("--duracao-max", type=float, metavar="HORAS", help="duração máxima de cada sentido, com escalas")
    g = p.add_argument_group("outros")
    g.add_argument("--top", type=int, default=10, help="quantos resultados mostrar (padrão 10)")
    g.add_argument("--reservas", type=int, default=0, metavar="N",
                   help="consulta o preço das agências para os N mais baratos (SerpApi, 3 buscas cada)")
    g.add_argument("--salvar", action="store_true", help="adiciona a rota ao config.yaml para ser monitorada")
    g.add_argument("--nome", help="nome da rota ao salvar (padrão: ORIGEM → DESTINO)")
    g.add_argument("--queda", type=float, default=10, help="ao salvar: alerta se o preço cair N%% (padrão 10)")
    g.add_argument("--forcar", action="store_true", help=f"permite mais de {LIMITE_SEM_CONFIRMAR} buscas de uma vez")
    g = p.add_argument_group("gerenciar as buscas salvas")
    g.add_argument("--listar", action="store_true", help="mostra as buscas salvas e quantas vagas restam")
    g.add_argument("--pausar", metavar="NOME", help="para uma busca sem apagá-la (não gasta pesquisas)")
    g.add_argument("--retomar", metavar="NOME", help="reativa uma busca pausada")
    g.add_argument("--remover", metavar="NOME", help="apaga uma busca salva")
    args = p.parse_args()
    for acao in ("listar", "pausar", "retomar", "remover"):
        if getattr(args, acao):
            gerenciar(acao, None if acao == "listar" else getattr(args, acao))
            return
    if not (args.origem and args.destino):
        p.error("informe --origem e --destino (ou use --listar, --pausar, --retomar, --remover)")
    if not (args.ida_entre or args.datas):
        p.error("informe as datas com --ida-entre e/ou --datas")

    load_dotenv(PASTA / ".env")
    geral = yaml.safe_load(CAMINHO_CONFIG.read_text(encoding="utf-8"))["geral"]
    moeda = geral.get("moeda", "BRL")
    rota = montar_rota(args)
    pares = combinacoes(rota.get("ida_entre"), rota.get("passo_dias", 1), rota.get("duracoes_dias"), datas=rota.get("datas"))
    if not pares:
        raise SystemExit("Nenhuma data no futuro para buscar.")
    if len(pares) > LIMITE_SEM_CONFIRMAR and not args.forcar:
        raise SystemExit(f"São {len(pares)} buscas; muitas de uma vez podem bloquear o Google. "
                         f"Reduza as datas ou use --forcar.")

    print(f"{rota['nome']}: {len(pares)} combinação(ões) de datas, "
          f"{rota['adultos']} adulto(s), {rota['criancas']} criança(s), {rota['bebes_colo']} bebê(s)\n")
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
                escalas_max=args.escalas_max, duracao_max_horas=args.duracao_max,
            )
        except Exception as erro:
            print(f"[{i}/{len(pares)}] {datas}: falhou ({erro})")
            continue
        # O preço máximo só é aplicado no fim, depois do preço das agências (--reservas).
        aprovados = [v for v in voos if passa(v, rota["filtros"], ignorar_preco=True)]
        if aprovados:
            melhor = min(aprovados, key=lambda v: v.preco)
            melhores.append(melhor)
            print(f"[{i}/{len(pares)}] {datas}: {len(aprovados)} voo(s), melhor {dinheiro(melhor.preco, moeda)}")
        else:
            print(f"[{i}/{len(pares)}] {datas}: {len(voos)} voo(s), nenhum nos filtros")

    melhores.sort(key=lambda v: v.preco)
    if melhores and args.reservas:
        consultar_reservas(rota, melhores[:args.reservas], moeda)
    melhores = sorted((v for v in melhores if passa(v, rota["filtros"])), key=lambda v: v.menor_preco)
    if melhores:
        print(f"\nMelhores opções (preço total, ida e volta):\n")
        for v in melhores[:args.top]:
            datas = f"{v.ida:%d/%m} → {v.volta:%d/%m} ({(v.volta - v.ida).days} dias)" if v.volta else f"{v.ida:%d/%m} (só ida)"
            escalas = "direto" if v.escalas == 0 else f"{v.escalas} escala(s)"
            partida = datetime.strptime(v.partida, "%Y-%m-%d %H:%M")
            print(f"{dinheiro(v.preco, moeda)} · {datas} · {escalas} · ida {v.duracao_min // 60}h{v.duracao_min % 60:02d}"
                  f" · sai {partida:%H:%M} · {v.companhias}")
            if v.reserva_preco:
                print(f"  → {dinheiro(v.reserva_preco, moeda)} em {v.reserva_onde}")
            print(f"  {v.link}\n")
    else:
        print("\nNenhum voo passou nos filtros.")

    if args.salvar:
        salvar_no_config(rota)
        print(f"Rota {rota['nome']!r} adicionada ao config.yaml; a tarefa agendada passa a monitorá-la.")


if __name__ == "__main__":
    main()
