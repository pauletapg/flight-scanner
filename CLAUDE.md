# Flight Scanner

Busca voos no Google Flights (fast-flights), guarda o histórico em SQLite e avisa no celular (ntfy).
Detalhes de uso no README.md. Textos, comentários e documentação em português do Brasil.

## Comandos

- Testes: `.\.venv\Scripts\python.exe -m pytest`
- Execução sem enviar alerta: `.\.venv\Scripts\python.exe -m scanner.main --dry-run`
- Busca avulsa / rotas salvas: `.\.venv\Scripts\python.exe -m scanner.buscar --listar`
- Interface (servidor): `.\.venv\Scripts\python.exe -m uvicorn scanner.web.app:app --port 8765`
  (neste PC a 8765 pode estar ocupada por outro projeto, o `ferramentas\servidor.py`; use outra porta para testar)

## Convenções

- Rotas monitoradas ficam no `config.yaml`; máximo de 3 ativas (`MAX_ROTAS` em `scanner/main.py`).
- Toda edição de rotas passa por `scanner/rotas.py` (preserva comentários, grava de forma atômica, erros como
  exceções `ErroRota`); a busca avulsa é `scanner/busca_avulsa.buscar` com callback de progresso.
  A CLI (`scanner/buscar.py`) só cuida de argparse, print e input.
- A interface web fica em `scanner/web/`: `app.py` só traduz para HTTP (`criar_app(...)` recebe caminhos de
  config, banco e log, a consulta da tarefa agendada e o comando do scanner, para os testes); `tarefas.py` roda a
  busca avulsa e o "Rodar agora" em segundo plano (um de cada por vez, 409 no segundo); `status.py` lê o log,
  a cota da SerpApi e o `schtasks` (colunas pela posição, porque os títulos mudam com o idioma).
- A página fica em `scanner/web/static/` (sem build, sem CDN): `index.html` (as 4 telas por `#hash`), `estilo.css`
  (direção visual e tokens de cor/tipo no topo; claro e escuro) e `app.js` (JavaScript puro; elementos criados com
  `h(...)`, nunca `innerHTML` com dados; `api()` lança `Error` com o `detail`). Os campos de rota ficam no
  `<template id="campos-rota">`, copiado para a edição e para "Buscar agora" no lugar de `[data-campos-rota]`;
  `lerFormularioRota`/`preencherFormularioRota` leem pelos nomes e ignoram os que o formulário não tem.
  Diálogos respondem por `esperarResposta(dialogo, aoConfirmar)`. Para ver no navegador embutido: configuração
  `interface` do `.claude/launch.json` (porta 8766, com `--reload`).
- Tela "Histórico" (`#historico`): `GET /api/historico?rota=...` (pontos por busca, alertas, `monitoradas` e `preco_max`
  da rota se ainda estiver no config) e `GET /api/relatorio` (horários). Os gráficos são SVG desenhados pelo próprio
  `app.js`, sem biblioteca: `s(...)` cria elementos SVG como `h(...)` cria HTML; `desenharGraficoPrecos` (linha por
  combinação de datas, uma em destaque, linha do `preco_max`, losangos nos alertas, dica e teclado), `graficoDesvios`
  (colunas por hora e dia da semana) e `desenharTabelaCombinacoes`. Cores de série nos tokens `--serie`,
  `--serie-quente` e `--serie-apagada` (claro e escuro; mexer só validando o par com a skill `dataviz`). Vários
  horários com até 2 min de diferença contam como uma busca. A rota atual nunca teve voo nos filtros, então a tela
  começa em "Todos os voos" quando não há nenhum ponto nos filtros.
- Cache do navegador: depois de editar `app.js`/`estilo.css`, recarregar com cache limpo (ou `fetch(url, {cache:"reload"})`
  e `location.reload()`); com `td`/`th` desencontrados ou comportamento antigo, é cache.
- Busca avulsa pela API: `POST /api/busca/previa` só conta as combinações (a página mostra antes e confirma acima
  de 30, mandando `forcar`); `GET /api/busca` devolve a busca em andamento ou a última, com a rota completa em
  `config` (a página retoma o progresso e o "Monitorar esta busca" usa essa rota, não o formulário).
- Erros da API sempre em `{"detail": "<mensagem em português>"}`; os de `ErroRota` levam também `ativas` ou `nomes`.
- Nos testes, `tests/conftest.py` aponta `rotas.CAMINHO_CONFIG` para um arquivo inexistente: quem precisa de
  config usa `tmp_path` (passando `caminho=` ou com monkeypatch). Nunca gravar no `config.yaml` real.
- `.env`, `data/`, `logs/` e `.venv` ficam fora do git.

Plano em etapas: plano.md; avançar com /continuar-etapa; diário de execução em progresso.md.
