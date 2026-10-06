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

## Etapa 3: Base visual e telas "Buscas monitoradas" e "Status e ações" · 2026-10-05 · concluída
**Modelo:** Opus 5.5 (a skill fixa Sonnet, mas a sessão mostrou Opus 5.5) · **Esforço:** medium

**O que foi feito**
- Direção visual registrada no topo de `scanner/web/static/estilo.css`: mesa de controle de tráfego aéreo; cada rota
  é uma "fita de progresso de voo" (campos separados por réguas, faixa lateral azul = monitorando, âmbar listrado =
  pausada). Bahnschrift condensada (DIN do Windows) para IATA, títulos e rótulos; Segoe UI no texto; Cascadia Mono
  nas saídas. Tokens de cor/espaço com tema claro e escuro (`prefers-color-scheme`). Sem CDN.
- `index.html`: topo com a próxima busca agendada, abas `#buscar`, `#rotas`, `#historico`, `#status` ("Buscar
  agora" e "Histórico" mostram "em breve"), diálogo de edição de rota e diálogo de confirmação.
- `app.js` (JavaScript puro): `h()` cria elementos sem `innerHTML`; `api()` lança `Error` com o `detail`.
  Buscas monitoradas: fitas, indicador "N de 3 vagas em uso", pausar/retomar, remover com confirmação, editar
  (formulário com intervalo de ida, datas avulsas em dd/mm/aaaa ou "ida a volta", durações, passageiros, classe,
  filtros e queda %) e aviso quando os passageiros mudam e o nome não. `lerFormularioRota` fica para a Etapa 4.
  Status: última execução, tarefa agendada (próxima, situação, último resultado), cota SerpApi com medidor,
  "Rodar sem enviar (teste)", "Rodar agora" (com confirmação), "Testar notificação", saída da execução e erros
  recentes resumidos na primeira linha (o resto num `<details>`).
- Layout de uma coluna no celular (fitas em 2 colunas de campos, abas compactas).
- `tests/test_web.py`: a página tem as 4 abas e serve `estilo.css` e `app.js` com o tipo certo.
- `tests/conftest.py`: fixture automática que apaga `NTFY_TOPIC`, `NTFY_SERVER`, `CALLMEBOT_*` e `SERPAPI_KEY`.
- `.claude/launch.json`: configuração `interface` (uvicorn na 8766, com `--reload`). `CLAUDE.md` atualizado.

**Skills usadas**
- anthropic-skills:frontend-design: direção visual (fita de progresso de voo, DIN, paleta de console) antes do código;
  revisada contra os visuais genéricos (creme+terracota, preto+verde ácido, jornal).
- run: não carregada como skill; o servidor subiu pelo `preview_start` com o `.claude/launch.json` (mesmo efeito).
- anthropic-skills:built-in-browser: telas testadas no navegador embutido (claro, escuro, 375 px), console sem erros.

**Desvios do plano**
- Testado na porta 8766, não na 8765 (ocupada pelo `ferramentas\servidor.py` de outro projeto, como na Etapa 2).
- Tela inicial sem `#hash` é "Buscas monitoradas", enquanto "Buscar agora" não existe (constante `TELA_INICIAL`
  no `app.js`; a Etapa 4 pode trocar).
- Os testes de editar e remover pela interface foram feitos num segundo servidor apontando para uma cópia do
  `config.yaml` e do banco (script no scratchpad), para não mexer na rota real. Pausar/retomar foi feito no real.
- Correção fora do escopo, em `tests/conftest.py` (ver Problemas): proteção das chaves do `.env` nos testes.

**Problemas e correções**
- **Duas notificações de teste reais foram enviadas ao celular.** Testei "Testar notificação" no servidor da cópia
  achando que ele não teria as chaves (o `criar_app` sem `arquivo_env` não lê o `.env`). Causa: o `fast_flights`
  chama `load_dotenv()` quando é importado, então qualquer processo que importe `scanner.pesquisa` (inclusive os
  testes) fica com o `.env` real no ambiente. O diário da Etapa 2 dizia que importar o app não carregava as
  chaves; isso estava errado. Correção para os testes: fixture `sem_chaves_reais` no `conftest.py`.
- O `<dialog>` de confirmação não removia: com o painel do navegador escondido, o evento `close` do diálogo não
  dispara (reproduzido isolado). `confirmar()` passou a responder pelo `submit` (síncrono, com `submitter`) e
  pelo `cancel` (Esc), sem depender do `close`.
- Pausei a rota real às 21:06 achando que a próxima execução era às 23:00, mas a das 21:05 estava rodando. Ela
  já tinha lido o config no início (fez 10 de 12 combinações) e a rota foi retomada segundos depois; o
  `config.yaml` voltou idêntico (sha256 `a704540…`). Para a próxima vez: olhar "Última execução" antes de pausar.
- Um `sed` para trocar `\r` na saída inseriu um CR literal na regex do `app.js` (sintaxe quebrada); corrigido
  com Python e conferido com `node --check`. Mesmo problema de escape no shell das Etapas 1 e 2.
- Placeholders do formulário pareciam valores preenchidos; ganharam "ex.:" e cor mais clara. A data na lista de
  erros quebrava em duas linhas (coluna fixa); passou a `max-content`. A aba "Status" ficava cortada a 375 px.
- Quadros do status ficavam vazios por ~2 s (o `schtasks` é lento); ganharam "Carregando…".

**Observações**
- Com o painel do navegador embutido escondido, cliques por coordenada e capturas falham e os timers atrasam;
  `element.click()` por JavaScript funciona para testar.
- O "Rodar sem enviar" é uma execução de verdade: faz as buscas, grava preços e avança o rodízio (só não envia).
- A saída do "Rodar agora" só chega no fim (o subprocesso não é lido aos poucos); a tela mostra "rodando desde…".
- `pydantic` recusa datas impossíveis (31/02) com 422 "Dados inválidos em rota.datas.0: valor inválido".

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 100 passaram, 0 falharam.
- Pausar e retomar no navegador embutido (porta 8766) mudou o `config.yaml`: `buscar --listar` mostrou
  `[PAUSADA]` e depois `[ativa]`; o arquivo voltou idêntico byte a byte. ok.
- Status mostra a cota real (15 de 240, 0 hoje) e a tarefa `VooScanner` (habilitada, próxima às 23:00). ok.
- "Rodar sem enviar" real: rodou de 21:09 a 21:10, saída com as 10 buscas e "Fim: nenhum alerta" na página. ok.
- Console do navegador sem erros (8766 e cópia). ok.
- Na cópia: editar (passageiros, nome, par ida/volta) gravou no mesmo formato da CLI com os comentários
  preservados; remover pede confirmação, Cancelar não remove; retomar com 3 ativas mostra a recusa. ok.

**Pendências**
- O `fast_flights` carrega o `.env` ao ser importado (afeta qualquer processo do projeto). Os testes estão
  protegidos; a Etapa 8 pode avaliar se vale mais alguma proteção.
- Etapa 4: reaproveitar `lerFormularioRota`/`preencherFormularioRota` e trocar `TELA_INICIAL` para `buscar`.
- A porta 8765 continua ocupada pelo outro programa (decisão da Etapa 6).

## Etapa 4: Tela "Buscar agora" · 2026-10-05 · concluída
**Modelo:** Opus 5.5 (a skill fixa Sonnet, mas a sessão mostrou Opus 5.5) · **Esforço:** medium

**O que foi feito**
- API: `POST /api/busca/previa` (conta as combinações sem buscar: `n`, `limite`, `nome`) e `GET /api/busca`
  (a busca em andamento ou a última). O estado da busca ganhou `config`, a rota completa no formato do config.
  `tarefas.Buscas.atual()`.
- `index.html`: os campos de rota saíram do diálogo de edição para o `<template id="campos-rota">`, copiado para a
  edição e para a busca. Tela "Buscar agora": formulário (os campos da CLI, mais "Resultados a mostrar" (top) e
  "Consultar o preço das agências" (reservas)), contagem de buscas ao vivo, quadro de progresso, resultados,
  "Monitorar esta busca" e o diálogo "As 3 vagas estão em uso".
- `app.js`: `esperarResposta(dialogo, aoConfirmar)` (o mecanismo do `confirmar` da Etapa 3, generalizado);
  prévia com atraso de 400 ms e descarte de respostas fora de ordem; confirmação acima de 30 (manda `forcar`);
  acompanhamento a cada 1,5 s (continua em outra tela e avisa no fim); botão travado em "Buscando…"; ao abrir a
  tela, retoma a busca em andamento ou mostra a última (e refaz o formulário, se a pessoa ainda não mexeu nele);
  resultados como fitas (preço total em destaque, agência quando mais barata, datas com dia da semana e dias,
  saída, chegada (+1 dia), escalas, duração da ida, companhias, link); "Mostrar todas as N opções" além do top;
  "Monitorar" usa a rota buscada (não o formulário) e, com 409 + `ativas`, pergunta qual substituir.
  `TELA_INICIAL` passou a `buscar`.
- `estilo.css`: régua da busca (uma casa por combinação: azul = achou voo, hachurada = nenhum nos filtros,
  vermelha = falhou, contorno piscando = buscando agora), legenda, fitas de voo, opções do diálogo,
  `.quadro[hidden]`.
- `tests/test_web.py`: 2 testes novos (prévia e busca atual). `CLAUDE.md` atualizado.

**Skills usadas**
- anthropic-skills:frontend-design: a direção da Etapa 3 foi mantida; a peça nova (a régua com uma casa por
  combinação, no mesmo desenho das vagas) foi escolhida para mostrar o resultado de cada data, não só a porcentagem.
- run: não carregada como skill; o `preview_start` da configuração `interface` recusou a porta 8766 (servidor de
  outra conversa) e abri a página pelo endereço (ver Desvios).
- anthropic-skills:built-in-browser: busca real, monitorar e remover na 8766; o resto num servidor de cópia.
- superpowers:test-driven-development (fora da lista): os 2 testes da API escritos antes e vistos falhando (404).

**Desvios do plano**
- Endpoints novos `POST /api/busca/previa` e `GET /api/busca`, que o plano não previa: a prévia evita repetir no
  JavaScript a conta de `filtros.combinacoes` (datas no passado, pares fixos, repetidas); a busca atual permite
  recarregar a página sem perder o progresso.
- A cor de cada casa da régua vem do texto da linha de progresso (`tipoLinha` no `app.js`: "falhou (",
  "nenhum nos filtros"). Se as mensagens de `busca_avulsa.buscar` mudarem, a régua perde as cores (a contagem
  continua certa).
- Testado com o servidor da 8766 de outra conversa (aberto com `--reload`, então serviu o código novo) e, para
  substituição, confirmação acima de 30, cores da régua e "mostrar todas", num servidor na 8767 com cópia do config
  (3 ativas) e buscador falso (script no scratchpad).

**Problemas e correções**
- Um "null" aparecia como texto embaixo dos resultados → `replaceChildren(..., null)` converte o `null` em texto
  (o `h()` filtra, o `replaceChildren` não) → monto a lista num array e só acrescento o botão quando precisa.
- O heredoc do Bash quebrou ao gravar o trecho de JavaScript ("unexpected EOF"); passei a usar a ferramenta de
  edição. Mesmo tipo de problema das Etapas 1 a 3.
- No servidor de cópia, o atraso do buscador falso (`time.sleep`) não funcionava: o script anulava
  `busca_avulsa.time.sleep`, que é o mesmo módulo `time`. Troquei por `threading.Event().wait` para ver o
  estado no meio da busca.
- O primeiro carregamento na 8766 teve um 404 em `GET /api/busca`: o JavaScript novo chegou antes de o
  `--reload` recarregar o Python. Sumiu ao recarregar.

**Observações**
- `preview_start` com uma URL `http://127.0.0.1:<porta>` abre no navegador embutido um servidor que esta sessão não
  iniciou (outra conversa, ou um script em segundo plano).
- A rota criada pela interface sem filtros grava `filtros: {}` (mesmo formato da Etapa 2).
- O estado das buscas fica na memória do servidor: reiniciar o servidor apaga a "última busca".

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 102 passaram, 0 falharam. `node --check app.js`: ok.
- Busca real pequena (GIG → REC, ida 20/11/2026, 5 dias, 1 adulto) no navegador embutido: progresso `[0/1]` →
  `[1/1]`, botão travado durante a busca, resultado R$ 1.134 (Gol, direto, 11:05) com o link do Google Flights. ok.
- Recarregar a página trouxe de volta o formulário e os resultados da última busca. ok.
- "Monitorar" (nome "Teste Etapa 4 (GIG → REC)", queda 15%) gravou a rota no `config.yaml` real no formato da
  CLI; `buscar --listar` e a tela "Monitoradas" mostraram a rota (2 de 3 vagas); removida pela interface e o
  `config.yaml` voltou idêntico (sha256 `a704540…`). ok.
- Na cópia: contagem "35 buscas … acima de 30, pede confirmação"; Cancelar não busca; confirmar faz as 35. Régua
  com casas achou/nenhum/falhou e a casa atual piscando; a segunda busca ao mesmo tempo responde 409. "Mostrando 10
  de 30" e "Mostrar todas". Com 3 ativas, "Monitorar" abre o diálogo (Substituir desabilitado até escolher;
  Cancelar não muda nada; substituir "Copia C" funcionou). Edição de rota depois da troca para `<template>`:
  campos preenchidos, aviso de passageiros, salvar. ok.
- 375 px no modo escuro sem rolagem horizontal. Console: só os 409 provocados de propósito. ok.

**Pendências**
- O `fast_flights` carrega o `.env` ao ser importado (pendência da Etapa 3, para a Etapa 8).
- A porta 8765 continua ocupada pelo outro programa (decisão da Etapa 6).
- Etapa 5: o histórico pode reaproveitar `fita`/`campo`, `diaCurto` e `textoPassageiros` do `app.js`.

## Etapa 5: Tela "Histórico e gráficos" · 2026-10-05 · em andamento
**Modelo:** Opus 5.5 (a skill fixa Sonnet, mas a sessão mostrou Opus 5.5) · **Esforço:** medium

**O que foi feito**
- API: `GET /api/historico` ganhou `monitoradas` (nomes das rotas do config) e `preco_max` (da rota escolhida, se
  ainda estiver no config). 2 testes em `tests/test_web.py`, escritos antes e vistos falhando (KeyError).
- `index.html`: tela "Histórico" com seletor de rota (grupos "Monitoradas" e "Removidas (só no histórico)"),
  alternância "Só voos nos filtros / Todos os voos", gráfico, tabela "menor preço já visto por combinação de datas",
  alertas enviados e "Horários das buscas".
- `app.js`: `s()` (SVG; `h()` e `s()` usam `preencher`), `organizarHistorico`, `desenharGraficoPrecos` (linha por
  combinação, a em destaque em azul e as outras em cinza, linha do preço máximo, losangos nos alertas, rótulo só no
  último ponto, mira com dica, teclado: setas/Home/End/Enter, clique destaca a mais barata da busca),
  `desenharTabelaCombinacoes` (clique ou Enter destaca a linha no gráfico), `desenharAlertas`, `graficoDesvios`
  (colunas divergentes por hora e por dia da semana, dica por coluna, aviso de poucos dados) e redesenho por
  `ResizeObserver`.
- `estilo.css`: tokens `--serie`, `--serie-quente`, `--serie-apagada` (claro e escuro) e estilos da tela; `.em-breve` removido.

**Skills usadas**
- dataviz: forma (linha com destaque + cinza; colunas divergentes), marcas (2 px, pontos r=4 com anel, cantos de 4 px
  na ponta), dica com valor em destaque, legenda sempre presente. Par azul/laranja validado com `validate_palette.js`
  nos dois temas; o azul escuro `#5B9BD8` falhou na faixa de luminosidade e virou `#5294D2`.
- run: não carregada; `preview_start` da `interface` recusou a 8766 (servidor de outra conversa, com `--reload`);
  abri pela URL, como na Etapa 4.
- anthropic-skills:built-in-browser: testes no navegador embutido (painel escondido, viewport emulado em 1280x900).
- superpowers:test-driven-development (fora da lista): os 2 testes da API.

**Desvios do plano**
- Alternância "Só voos nos filtros / Todos os voos" (vale para gráfico e tabela): a rota monitorada hoje (3
  passageiros, preço máximo R$ 5.000) nunca teve voo nos filtros (mínimo R$ 6.576), então o gráfico do plano ficaria
  vazio. Sem dados nos filtros, começa em "todos" com aviso explicando.
- Horários seguidos com até 2 min de diferença contam como uma busca (o banco antigo grava um horário por
  combinação); alerta pertence à busca se foi gravado até 2 min depois do fim dela.
- Linha do preço máximo só entra no gráfico se estiver entre 70% do menor e 130% do maior preço; senão a legenda
  diz que está acima/abaixo.

**Problemas e correções**
- Primeiro carregamento: TypeError em `lista.monitoradas.includes` → o JS novo chegou antes do `--reload` do Python
  → sumiu ao recarregar (o erro continua no histórico do console da aba).
- Com o painel escondido a largura era 0 e o `ResizeObserver` não disparava → `resize_window` 1280x900 e recarregar.
- Um script Python de substituição tinha um padrão errado; o `assert` parou antes de gravar. Refeito com o Edit.
- Na dica, a chave da série em destaque não aparecia (`chave: ""` é falso) → `"destaque"`. Eixo dos horários
  arredondava 2,5% para "3%" → uma casa decimal. Com empate, a dica mostrava "mais barato" com o mesmo preço → só
  quando é realmente menor. Alertas antigos não apareciam na dica (gravados depois do último horário) → janela de 2 min.

**Observações**
- `navigate` para a mesma URL com `#hash` não recarrega a página; usar `location.reload()`.
- Com o documento sem foco (painel escondido), `focus`/`blur` não disparam sozinhos; o tratador do blur foi conferido
  disparando o evento.

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 103 passaram, 0 falharam. `node --check app.js`: ok.
- Rota "Rio → Recife (2 adultos + 1 criança)": os 9 pontos da combinação em destaque, lidos de volta da posição no
  SVG pela escala do eixo, batem com `SELECT buscado_em, MIN(preco) ... GROUP BY buscado_em` (10.272, 10.199 ×5,
  6.576 ×3). ok.
- "Rio → Recife (Natal 2026)": tabela confere com SQL (R$ 1.721 em 04/10 01:18; última busca sem voo nos filtros);
  5 alertas na lista e 5 losangos; dica mostra data, hora, preço e os alertas daquela busca. ok.
- Console: só o erro do primeiro carregamento (antes do reload do servidor). ok.
- NÃO conferido ainda: 375 px e tema escuro.

**Pendências**
- Conferir a tela a 375 px e no tema escuro; depois atualizar o `CLAUDE.md` (tela de histórico, `s()`, tokens
  `--serie*`) e commitar como `Etapa 5: ...`.
- O `fast_flights` carrega o `.env` ao ser importado (para a Etapa 8). A porta 8765 continua ocupada (Etapa 6).

## Etapa 5: Tela "Histórico e gráficos" (retomada) · 2026-10-06 · concluída
**Modelo:** Sonnet 5.5 · **Esforço:** medium

**O que foi feito**
- Fechamento da Etapa 5 a partir das alterações não commitadas da entrada anterior (o trabalho de código já estava
  feito; faltava conferir 375 px e o tema escuro, atualizar o `CLAUDE.md` e commitar).
- Tabela "menor preço já visto por combinação de datas" a 375 px: o preço (coluna mais importante) ficava fora da
  tela, atrás de "Dias" e de um cabeçalho de 166 px. Em `@media (max-width: 520px)`: coluna "Dias" escondida
  (`.coluna-dias` no `th` em `index.html` e no `td` em `app.js`), espaçamento lateral menor e cabeçalhos podem
  quebrar linha. As colunas "Visto em", "Última busca" e "Buscas" continuam por rolagem lateral dentro do cartão.
- `CLAUDE.md`: tela de histórico (API, `s()`, funções de desenho, tokens `--serie*`, regra dos 2 min) e a dica de cache
  do navegador.

**Skills usadas**
- dataviz: aplicada na entrada anterior; aqui só conferi o resultado nos dois temas.
- run: não carregada; `preview_start` da `interface` funcionou nesta sessão (a 8766 estava livre).
- anthropic-skills:built-in-browser: viewport 375x812 em claro e escuro, console e rede.

**Desvios do plano**
- Coluna "Dias" fica escondida a 520 px ou menos (dá para deduzir de ida e volta); no plano a tabela não previa
  tratamento para telas estreitas.

**Problemas e correções**
- Depois do ajuste, os valores de "Dias" apareceram sob o cabeçalho "Menor": o `estilo.css` novo já estava em uso, mas o
  `app.js` antigo vinha do cache do navegador (o `th` sumia e o `td` não). Corrigido recarregando com
  `fetch(url, {cache:"reload"})` + `location.reload()`; não era bug do código.
- Meu `fetch('/static/estilo.css')` de teste usou o caminho errado (os arquivos são servidos na raiz: `/estilo.css`) e
  deixou um 404 no console. Não vem da página.
- Captura de tela estourou o tempo duas vezes após trocar o esquema de cores; funcionou na repetição.

**Observações**
- Cache do navegador com a página estática pode mostrar HTML/CSS/JS de versões diferentes depois de uma edição; ao ver
  colunas ou comportamento desencontrados, recarregar com cache limpo antes de procurar bug.
- A 375 px nenhuma aba tem rolagem horizontal da página (`scrollWidth` 375 em Buscar, Monitoradas, Histórico e Status).

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 103 passaram, 0 falharam. `node --check app.js`: ok.
- "Pronto quando" da Etapa 5: gráfico de Rio → Recife com datas e preços conferindo com SQL direto e dica com data, hora e
  preço (conferidos na entrada anterior), sem erros no console (só o 404 do meu `fetch` de teste): ok.
- 375 px: sem rolagem horizontal da página; preço visível na tabela; gráfico, legenda e relatório de horários legíveis: ok.
- Tema escuro: gráfico de preços, linha do preço máximo, aviso, colunas de horários e tabela com contraste legível: ok.

**Pendências**
- O `fast_flights` carrega o `.env` ao ser importado (para a Etapa 8). A porta 8765 continua ocupada por outro projeto
  (`ferramentas\servidor.py`); a Etapa 6 precisa tratar isso ao subir o servidor no atalho.

## Etapa 6: Atalho de abertura e documentação · 2026-10-06 · concluída
**Modelo:** Sonnet 5.5 · **Esforço:** low

**O que foi feito**
- `Flight Scanner.cmd` (UTF-8, CRLF): se `GET /api/rotas` na 8765 já responde com `max_ativas`, só abre o navegador;
  se a porta é de outro programa, avisa e sai com código 1; senão sobe `pythonw -m uvicorn scanner.web.app:app
  --host 127.0.0.1 --port 8765 --no-access-log` (saída em `logs\interface.log`), espera até 30 s o servidor responder
  e abre a página. `Fast scanner.cmd` ficou como estava.
- `POST /api/desligar` em `scanner/web/app.py` (corpo `{"confirmar": true}` obrigatório; `criar_app(desligar=...)`
  para os testes; `encerrar_servidor()` manda SIGINT 0,5 s depois da resposta e usa `os._exit` se não sair em 5 s).
  2 testes em `tests/test_web.py`, escritos antes e vistos falhando (TypeError por `desligar` desconhecido).
- Tela de status: cartão "Interface" com o botão "Desligar interface" (diálogo de confirmação; depois a página vira
  "Interface desligada").
- `README.md`: seção "Interface gráfica" (como abrir, o que cada tela faz, log, porta ocupada, subir à mão).
  `CLAUDE.md`: o atalho, o `/api/desligar` e a dica de teste do `.cmd`.

**Skills usadas**
- run: não carregada; subi e conferi o atalho de verdade (processos, porta, log) e a página no navegador embutido.
- superpowers:test-driven-development (fora da lista): os 2 testes do `/api/desligar`.

**Desvios do plano**
- O corpo `{"confirmar": true}` no `/api/desligar` não estava no plano: serve para uma página de outro site não
  conseguir desligar o servidor com um POST simples (precisa de JSON, que exige preflight sem CORS liberado).
- O atalho confere que a 8765 é mesmo a interface (e não o `ferramentas\servidor.py`) em vez de só ver se a porta
  responde; o plano só dizia "se já estiver no ar".
- Um `.cmd` sempre abre uma janela de console por um instante; o servidor em si roda sem janela (pythonw) e a janela do
  atalho fecha sozinha ao terminar.

**Problemas e correções**
- `desligarInterface` usava `evento.currentTarget` depois do `await confirmar(...)`; vira `null` e `comBotao` quebrava
  antes do POST (console: "Cannot set properties of null"). Corrigido guardando o botão antes do `await`.
  Peguei no navegador, não nos testes: os testes de API não exercitam o JavaScript.
- Meu teste do `.cmd` pelo Git Bash falhou por aspas (`'Flight' não é reconhecido`), e pelo PowerShell a chamada ficou
  pendurada: o servidor herda a pipe da ferramenta e a chamada só termina quando ele fecha. No duplo clique não ocorre.
  Anotado no `CLAUDE.md`.
- Dois testes meus no navegador deram falso negativo: cliquei no botão por referência com o diálogo ainda sem abrir
  (nenhum POST saiu) e o `app.js` novo vinha do cache; refeito checando cada passo.

**Observações**
- O `pythonw.exe` do `.venv` é um launcher que abre o pythonw de verdade como filho: aparecem 2 processos; o SIGINT
  encerrou os dois e o log mostrou o desligamento normal ("Shutting down … Finished server process").
- A 8765 estava livre nesta sessão; simulei o outro programa com `python -m http.server 8765`, depois encerrei.
- O servidor sem `--reload` serve `app.js`/`estilo.css` do disco, mas o navegador pode ter cópia em cache.

**Verificação**
- `.\.venv\Scripts\python.exe -m pytest`: 105 passaram, 0 falharam. `node --check app.js`: ok.
- "Pronto quando": duplo clique (pelo PowerShell) sobe o servidor sem processo de console e a página abre em
  `http://127.0.0.1:8765` (`GET /api/rotas` 200, log em `logs\interface.log`): ok. Rodar de novo: saiu em 0,2 s com
  código 0 e continuou 1 servidor (2 processos com o launcher): ok. "Desligar interface": Cancelar não desliga;
  confirmar mostra "Interface desligada", a 8765 deixa de ouvir e os processos somem: ok.
- Porta ocupada por outro programa: mensagem em português com acentos, código 1, nenhum servidor novo: ok.
- NÃO conferido: o duplo clique real no Explorer (a janela do `.cmd` piscando e fechando) e a aba abrir no navegador
  padrão do usuário; usei a chamada pelo PowerShell.

**Pendências**
- Etapa 7 (opcional) depende de decisão do usuário e do firewall; a Etapa 8 deve revisar o `/api/desligar` e o
  `fast_flights` carregando o `.env` ao ser importado.
