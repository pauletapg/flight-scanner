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
  `h(...)`, nunca `innerHTML` com dados; `api()` lança `Error` com o `detail`; `lerFormularioRota` monta o corpo
  de `RotaEntrada` e serve também para a tela "Buscar agora"). Para ver no navegador embutido: configuração
  `interface` do `.claude/launch.json` (porta 8766, com `--reload`).
- Erros da API sempre em `{"detail": "<mensagem em português>"}`; os de `ErroRota` levam também `ativas` ou `nomes`.
- Nos testes, `tests/conftest.py` aponta `rotas.CAMINHO_CONFIG` para um arquivo inexistente: quem precisa de
  config usa `tmp_path` (passando `caminho=` ou com monkeypatch). Nunca gravar no `config.yaml` real.
- `.env`, `data/`, `logs/` e `.venv` ficam fora do git.

Plano em etapas: plano.md; avançar com /continuar-etapa; diário de execução em progresso.md.
