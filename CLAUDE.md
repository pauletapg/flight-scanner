# Flight Scanner

Busca voos no Google Flights (fast-flights), guarda o histórico em SQLite e avisa no celular (ntfy).
Detalhes de uso no README.md. Textos, comentários e documentação em português do Brasil.

## Comandos

- Testes: `.\.venv\Scripts\python.exe -m pytest`
- Execução sem enviar alerta: `.\.venv\Scripts\python.exe -m scanner.main --dry-run`
- Busca avulsa / rotas salvas: `.\.venv\Scripts\python.exe -m scanner.buscar --listar`

## Convenções

- Rotas monitoradas ficam no `config.yaml`; máximo de 3 ativas (`MAX_ROTAS` em `scanner/main.py`).
- Toda edição de rotas passa por `scanner/rotas.py` (preserva comentários, grava de forma atômica, erros como
  exceções `ErroRota`); a busca avulsa é `scanner/busca_avulsa.buscar` com callback de progresso.
  A CLI (`scanner/buscar.py`) só cuida de argparse, print e input.
- Nos testes, `tests/conftest.py` aponta `rotas.CAMINHO_CONFIG` para um arquivo inexistente: quem precisa de
  config usa `tmp_path` (passando `caminho=` ou com monkeypatch). Nunca gravar no `config.yaml` real.
- `.env`, `data/`, `logs/` e `.venv` ficam fora do git.

Plano em etapas: plano.md; avançar com /continuar-etapa; diário de execução em progresso.md.
