# Progresso

## Etapa 1: Extrair a lógica de rotas e da busca avulsa · 2026-10-05 · concluída
**Modelo:** Opus 5.5 · **Esforço:** medium

**O que foi feito**
- `scanner/rotas.py`: `listar`, `adicionar(rota, substituir=None)`, `editar(nome_antigo, rota)`, `pausar`, `retomar`
  (devolve quantas ficaram ativas) e `remover`, todas com `caminho=None` (= `CAMINHO_CONFIG`, resolvido na hora da
  chamada). Exceções `ErroRota` → `RotaNaoEncontrada` (`.nomes`), `NomeRepetido`, `VagasEsgotadas` (`.ativas`), com
  mensagem em português. Edição por blocos de texto (comentários preservados), YAML validado antes de gravar,
  gravação atômica (`tempfile.mkstemp` na mesma pasta + `os.replace`, com até 5 tentativas se o Windows recusar
  porque outro processo está lendo) e fim de linha preservado (o `config.yaml` real é CRLF).
- `scanner/busca_avulsa.py`: `combinacoes_da_rota(rota)`, `buscar(rota, geral, reservas=0, progresso=..., caminho_banco=...)`
  e `consultar_reservas` (movida de `buscar.py`); `LIMITE_SEM_CONFIRMAR` mudou para cá.
- `scanner/buscar.py`: passou a chamar `rotas` e `busca_avulsa`; ficou só com argparse, print, input e a exibição
  dos resultados (−124/+46 linhas).
- Testes novos: `tests/test_rotas.py` (19), `tests/test_busca_avulsa.py` (5), `tests/test_buscar_cli.py` (8, conferem
  as mensagens da CLI) e `tests/conftest.py` (proteção do config real).

**Skills usadas**
- superpowers:test-driven-development: testes de `rotas`, `busca_avulsa` e da CLI escritos antes e vistos falhando
  (ImportError dos módulos inexistentes; depois 7 falhas da CLI pelo caminho fixo, ver abaixo).

**Desvios do plano**
- `editar` não muda o estado pausada/ativa (ignora `pausada` no dicionário e mantém o da rota antiga); para isso
  existem `pausar`/`retomar`. Assim a interface não reativa sem querer uma rota e não fura o limite de 3.
- `retomar` não bloqueia acima de 3 ativas: devolve o número de ativas e a CLI mostra o aviso de antes (a saída da
  CLI tinha de ficar igual). A Etapa 2/3 decide se a API recusa com 409.
- `adicionar` com `substituir` remove essa rota mesmo havendo vaga; se a substituída estava pausada e continuam 3
  ativas, dá `VagasEsgotadas`.
- Mensagens das reservas saem pelo callback com `i` e `n` iguais a `None`; a CLI põe a linha em branco antes do
  primeiro desses avisos, para a saída ficar igual.
- Além do `test_rotas.py` previsto, criei `test_busca_avulsa.py`, `test_buscar_cli.py` e `conftest.py`.

**Problemas e correções**
- **Testes gravaram no `config.yaml` real** → os parâmetros eram `caminho: Path = CAMINHO_CONFIG`, avaliados na
  definição; o monkeypatch de `rotas.CAMINHO_CONFIG` em `test_buscar_cli.py` não tinha efeito e
  `test_salvar_com_nome_repetido`/`test_salvar_substituindo` acrescentaram as rotas falsas "A" e "D" no config real
  (por volta de 20:29) → restaurado com `git checkout -- config.yaml` (o arquivo estava igual ao commit; hash
  `a704540…` conferido). A última execução agendada foi às 19:46, antes disso. Correção: padrão `None` resolvido em
  `_ler` e `tests/conftest.py` com fixture automática que aponta o caminho padrão para um arquivo inexistente.
- Edições por script Python via heredoc no Bash falharam duas vezes (escapes `\\n` e acentos lidos com a codificação
  errada); passei a usar um script em arquivo com `-X utf8` e a ferramenta de edição.
- `test_busca_mostra_progresso_e_resultados` esperava "RIO → REC" com `--origem rio`; o nome padrão usa o texto
  digitado (comportamento antigo de `montar_rota`), então corrigi o teste, não o código.

**Observações**
- As mensagens de `SystemExit` da CLI saem com acentos embaralhados no Git Bash porque vão para o stderr, que não é
  reconfigurado para UTF-8 (só o stdout é). Já era assim antes da etapa.
- `busca_avulsa.buscar` lê `escalas_max` e `duracao_max_horas` de `rota["filtros"]` (antes vinham direto dos args;
  dá no mesmo porque `montar_rota` só põe nos filtros o que não é None).
- Para a Etapa 2: usar `caminho=` explícito ou monkeypatch de `rotas.CAMINHO_CONFIG` (agora funciona); o
  `caminho_banco` de `busca_avulsa.buscar` permite banco temporário nos testes com `reservas`.

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 56 passaram, 0 falharam (24 antigos + 32 novos).
- `python -m scanner.buscar --listar`: saída idêntica byte a byte à capturada antes da etapa (`cmp`).
- `config.yaml` real igual byte a byte (sha256 `a704540…` no início e no fim); `test_config_real_ida_e_volta_byte_a_byte`
  faz pausar/retomar e adicionar/remover numa cópia dele e confere os bytes.
- Conferido à mão: `--remover` de nome inexistente, a tela de ajuda sem argumentos e o bloqueio acima de 30 buscas.

**Pendências**
- Etapa 2 precisa da aprovação para instalar `fastapi`, `uvicorn` e `httpx` no `.venv`.
