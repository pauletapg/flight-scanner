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

## Etapa 2: Servidor FastAPI e API · 2026-10-05 · concluída
**Modelo:** Opus 5.5 (a skill fixa Sonnet, mas a sessão mostrou Opus 5.5) · **Esforço:** medium

**O que foi feito**
- Instalados no `.venv` (com aprovação): `fastapi==0.142.2`, `uvicorn==0.54.0`, `httpx==0.28.1`, fixados no
  `requirements.txt`.
- `scanner/web/app.py`: `criar_app(caminho_config, caminho_banco, caminho_log, consultar_tarefas, comando_scanner,
  arquivo_env)` e `app = criar_app(arquivo_env=PASTA / ".env")` (o `.env` só é lido no lifespan, então importar o
  módulo nos testes não carrega as chaves reais). Endpoints: `GET/POST/PUT /api/rotas`, `POST /api/rotas/acao`,
  `POST /api/busca`, `GET /api/busca/{id}`, `GET /api/historico?rota=`, `GET /api/alertas?rota=&limite=`,
  `GET /api/relatorio`, `GET /api/status`, `POST/GET /api/executar`, `POST /api/notificacao-teste`; estáticos em `/`.
  Modelo `RotaEntrada` (pydantic) + `montar_rota`, que grava no config na mesma ordem de campos da CLI.
- `scanner/web/tarefas.py`: `Buscas` (thread, uma por vez, estado com i/n, linhas, resultados e erro) e
  `Execucoes` (subprocesso `python -m scanner.main [--dry-run]`, stdout+stderr juntos, `PYTHONIOENCODING=utf-8`,
  `CREATE_NO_WINDOW`, limite de 30 min). Ambos lançam `Ocupado` → 409.
- `scanner/web/status.py`: `ler_fim` (só os últimos 200 KB do log), `entradas` (junta traceback e texto do alerta à
  linha anterior), `ultima_execucao`, `erros_recentes` (WARNING/ERROR/CRITICAL, mais novo primeiro),
  `ler_schtasks`/`consultar_tarefas` (FlightScanner e VooScanner) e `obter`.
- `scanner/relatorio.py`: `dados(con)` devolve por rota `buscas`, `combinacoes`, `por_hora` e `por_dia`; `gerar()`
  passou a formatar a partir dele.
- `scanner/notificar.py`: `enviar_teste()` extraída do `__main__`, usada pela CLI e pela API.
- `scanner/web/static/index.html` provisório.
- Testes novos: `tests/test_web.py` (30), `tests/test_web_status.py` (10), `tests/test_relatorio.py` (3).

**Skills usadas**
- superpowers:test-driven-development: testes do relatório, do status e da API escritos antes; vistos falhando
  (AttributeError de `relatorio.dados`, ImportError de `scanner.web.status` e de `scanner.web.app`).
  O teste do texto do relatório é de caracterização (passou antes do refatoramento, de propósito).
- headroom:peek: não usada. O `logs\scanner.log` real tem 63 KB; `tail` e `grep` bastaram para ver o formato.

**Desvios do plano**
- `POST /api/rotas/acao` com `retomar` responde 409 (com `ativas`) se já houver 3 ativas; a CLI continua só
  avisando. Decisão que a Etapa 1 deixou para cá.
- `POST /api/busca` recusa com 422 acima de `LIMITE_SEM_CONFIRMAR` (30) sem `forcar: true`, e sem datas no futuro.
- `GET /api/historico` sem `rota` devolve só a lista de rotas do banco (`pontos` vazio); com `rota`, um ponto por
  busca e combinação de datas, com `menor_preco` (todos os voos) e `menor_nos_filtros`.
- `GET /api/executar` (não previsto) devolve a última execução do "Rodar agora"; o `/api/status` também traz em
  `execucao`.
- Erros de validação do pydantic viram 422 `{"detail": "Dados inválidos em <campo>: <motivo>"}` em português.
- Testes de status num arquivo à parte (`test_web_status.py`) e do relatório em `test_relatorio.py`.
- `pytest.ini` ganhou `filterwarnings` para o aviso do Starlette 1.7 ("use httpx2 em vez de httpx"): trocar
  exigiria outro pacote não aprovado, e o httpx funciona.

**Problemas e correções**
- O heredoc do Git Bash transformou `\n` em quebra de linha de verdade duas vezes (no script que reescreveu
  `relatorio.py`, o que deu SyntaxError, e no de `notificar.py`, onde o assert não achou o trecho). É o mesmo
  problema da Etapa 1; corrigi com a ferramenta de edição. Para a próxima vez: nada de `\n` em heredoc, usar o Edit.
- O script de conferência no scratchpad deu `ModuleNotFoundError: scanner` → faltava `PYTHONPATH=.` fora do pytest.
- `uvicorn --port 8765` falhou (WinError 10048): a porta está ocupada por outro programa do usuário,
  `python ferramentas\servidor.py` (PID 8068, aberto às 19:42, de outro projeto). Não mexi nele; o curl na 8765
  devolvia a página 404 do `http.server`, o que primeiro pareceu erro da API. Verifiquei na porta 8766.
- `curl --data-urlencode "rota=Rio → Recife ..."` no Git Bash devolveu `pontos` vazio; com Python (`urllib`) vieram os
  80 pontos. Problema de codificação do argumento no Git Bash, não da API.

**Observações**
- O schtasks (Windows em português) sai em cp850 e com uma linha por gatilho; a próxima execução é a menor entre as
  linhas. As datas vêm em dd/mm/aaaa e a API devolve ISO.
- Os avisos antigos do log ("WhatsApp não configurado ... Alerta não enviado:") trazem a mensagem inteira do alerta
  (vários KB cada); a tela de status (Etapa 3) deve mostrar só a primeira linha e expandir sob demanda.
- Se o log acabou de girar (`RotatingFileHandler`, 1 MB), o último "Início" pode estar no `scanner.log.1`; hoje
  isso aparece como "sem execução" até a próxima rodada.
- O "Rodar agora" real não foi disparado: mesmo em `--dry-run` ele faz 10 buscas de verdade no Google. Os testes
  usam um comando falso (`python -c ...`).
- A interface pode receber `datas` como `["2027-02-01", ["2027-03-01", "2027-03-10"]]` (data avulsa ou par
  ida/volta), como a CLI.

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 99 passaram, 0 falharam (56 antigos + 43 novos), sem avisos.
- Pronto quando: o uvicorn sobe (na 8766, porque a 8765 está ocupada por outro programa) e `GET /api/rotas` e
  `/api/status` devolvem JSON com os dados reais: a rota "Rio → Recife (2 adultos + 1 criança)", a última execução
  das 19:45–19:46, 15 consultas da SerpApi no mês, a tarefa `VooScanner` com a próxima execução. Também conferidos
  com dados reais `/api/historico` (80 pontos por rota), `/api/alertas`, `/api/relatorio` e `/`.
- `python -m scanner.relatorio`: saída real idêntica antes e depois do refatoramento (`cmp`).
- Rota criada pela API numa cópia do `config.yaml` sai no mesmo formato YAML da CLI; o `config.yaml` real ficou
  igual (sha256 `a704540…` no início e no fim).

**Pendências**
- A porta 8765 está ocupada neste PC pelo `ferramentas\servidor.py` de outro projeto. A Etapa 6 (atalho) precisa
  decidir: outra porta fixa ou detectar a porta livre.
- Etapa 3: mostrar os erros do log resumidos (primeira linha), porque alguns avisos têm vários KB.
