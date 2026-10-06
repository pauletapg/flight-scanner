# Flight Scanner

Busca voos no Google Flights (fast-flights), guarda o histórico em SQLite e avisa no celular (ntfy).
Detalhes de uso no README.md. Textos, comentários e documentação em português do Brasil.

## Comandos

- Testes: `.\.venv\Scripts\python.exe -m pytest`
- Execução sem enviar alerta: `.\.venv\Scripts\python.exe -m scanner.main --dry-run` (faz as buscas de verdade, mas
  não grava preços no histórico nem avança o rodízio; só a cota da SerpApi e o cache das reservas ficam gravados)
- Busca avulsa / rotas salvas: `.\.venv\Scripts\python.exe -m scanner.buscar --listar`
- Interface (servidor): `.\.venv\Scripts\python.exe -m uvicorn scanner.web.app:app --port 8765`
  (neste PC a 8765 pode estar ocupada por outro projeto, o `ferramentas\servidor.py`; use outra porta para testar)
- Atalho do usuário: `Flight Scanner.cmd` (duplo clique). Se `GET /api/rotas` já responde com `max_ativas` na 8765, só
  abre o navegador; se a porta é de outro programa, avisa e sai com 1; senão sobe `pythonw -m uvicorn ...
  --no-access-log` com a saída em `logs\interface.log` e abre a página quando o servidor responde. Encerra-se pelo
  botão "Desligar interface" (`POST /api/desligar` com `{"confirmar": true}`: SIGINT depois de 0,5 s, `os._exit`
  se não sair em 5 s). Para testar o `.cmd` por ferramenta, o servidor herda a pipe da chamada e ela só termina
  quando o servidor fecha: rode em segundo plano ou desligue o servidor logo depois. Arquivo em UTF-8 com CRLF.
- Acesso pelo celular: `Flight Scanner.cmd --rede` (ou o `Flight Scanner (celular).cmd`, que o chama) sobe com
  `--host 0.0.0.0` e `FLIGHT_SCANNER_REDE=1`; o app então exige token. Se já houver servidor em modo local, avisa e
  sai com 1. Ao subir o uvicorn à mão com `pythonw`, redirecione a saída (sem ela `sys.stdout` é `None` e o log quebra).

## Convenções

- Rotas monitoradas ficam no `config.yaml`; máximo de 3 ativas (`MAX_ROTAS` em `scanner/main.py`).
- Toda edição de rotas passa por `scanner/rotas.py` (preserva comentários, grava de forma atômica, erros como
  exceções `ErroRota`), assim como `rotas.montar_rota` (a rota no formato do config, para CLI e API) e
  `rotas.ativas`; a busca avulsa é `scanner/busca_avulsa.buscar` com callback de progresso.
  A CLI (`scanner/buscar.py`) só cuida de argparse, print e input.
- A interface web fica em `scanner/web/`: `app.py` só traduz para HTTP (`criar_app(...)` recebe caminhos de
  config, banco e log, a consulta da tarefa agendada e o comando do scanner, para os testes); `tarefas.py` roda a
  busca avulsa e o "Rodar agora" em segundo plano (um de cada por vez, 409 no segundo; o "Rodar agora" também dá
  409 se o log mostra um "Início" sem "Fim" de menos de 20 min, `status.execucao_em_andamento`); `status.py` lê o log,
  a cota da SerpApi e o `schtasks` (colunas pela posição, porque os títulos mudam com o idioma).
- A página fica em `scanner/web/static/` (sem build, sem CDN): `index.html` (as 4 telas por `#hash`), `estilo.css`
  (direção visual e tokens de cor/tipo no topo; claro e escuro) e `app.js` (JavaScript puro; elementos criados com
  `h(...)`, nunca `innerHTML` com dados; `api()` lança `Error` com o `detail`). Os campos de rota ficam no
  `<template id="campos-rota">`, copiado para a edição e para "Buscar agora" no lugar de `[data-campos-rota]`;
  `lerFormularioRota`/`preencherFormularioRota` leem pelos nomes e ignoram os que o formulário não tem.
  Diálogos respondem por `esperarResposta(dialogo, aoConfirmar)`. Para ver no navegador embutido: configuração
  `interface` do `.claude/launch.json` (porta 8767, com `--reload`; a 8766 pode estar ocupada por outro projeto).
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
- Acesso (`scanner/web/acesso.py`, um middleware ligado por `criar_app(token=...)`): "é o PC" = IP de origem loopback
  **e** `Host` loopback (barra DNS rebinding). Sem token (modo local) o resto recebe 403; com token (modo rede,
  `FLIGHT_SCANNER_REDE=1`) recebe 401, e entra com `?t=` (GET vira cookie `HttpOnly`, `SameSite=Lax`, 303 sem o token na
  URL) ou com o cookie. O token vem de `INTERFACE_TOKEN` no `.env` (`garantir_token` gera e grava, preservando o resto
  e o CRLF; recusa token com menos de 20 caracteres). `GET /api/acesso` devolve os endereços com o token (todas as
  placas de rede privadas, a de saída primeiro). Toda ação que grava (POST/PUT/DELETE...) exige o cabeçalho
  `X-Flight-Scanner` (o `api()` do `app.js` manda; é a proteção contra CSRF, junto com `Origin` = `Host` e
  `Sec-Fetch-Site`), e toda resposta leva CSP (`style-src 'unsafe-inline'` só para o `style=` do `app.js`), `nosniff`,
  `X-Frame-Options`, `Referrer-Policy`; `/api/*` leva `no-store`. `/docs`, `/redoc` e `/openapi.json` estão desligados.
  Nos testes, use a fixture `abrir_cliente(app, ip=..., host=..., csrf=...)` (conftest): ela age como o navegador do PC;
  um `TestClient(app)` puro (IP `testclient`, sem o cabeçalho) leva 403. Os testes nunca gravam no `.env` real
  (`garantir_token` só com `tmp_path`).
- Nos testes, `tests/conftest.py` aponta `rotas.CAMINHO_CONFIG` para um arquivo inexistente: quem precisa de
  config usa `tmp_path` (passando `caminho=` ou com monkeypatch). Nunca gravar no `config.yaml` real.
- `.env`, `data/`, `logs/` e `.venv` ficam fora do git.

Plano em etapas: plano.md; avançar com /continuar-etapa; diário de execução em progresso.md.
