# plano.md: Interface gráfica do Flight Scanner

## 1. Contexto

Hoje o Flight Scanner só é usado pelo terminal: `scanner.buscar` (busca avulsa e gestão das rotas
salvas), `scanner.main` (execução da tarefa agendada), `scanner.relatorio` e `scanner.notificar --teste`.
O objetivo é ter uma interface gráfica que faça tudo isso sem digitar comandos.

Decisões tomadas com o usuário (2026-10-05):

- **Tipo:** app web local. Um servidor Python pequeno (FastAPI + uvicorn) serve uma página HTML que abre
  no navegador do PC por um atalho `.cmd`. Escuta só em `127.0.0.1`. O acesso pelo celular fica numa
  etapa opcional, porque exige proteção (a interface edita o `config.yaml`).
- **Telas (as 4):**
  1. **Buscar agora**: formulário da busca avulsa, progresso, resultados com link e botão "Monitorar esta busca".
  2. **Buscas monitoradas**: listar, pausar, retomar, remover e editar as rotas do `config.yaml` (máx. 3 ativas).
  3. **Histórico e gráficos**: preço ao longo do tempo por rota e por datas, alertas enviados, relatório de horários.
  4. **Status e ações**: última execução, erros do log, cota da SerpApi, tarefa agendada, "Rodar agora" e "Testar notificação".
- A CLI continua funcionando igual. A interface e a CLI usam as **mesmas funções**, sem lógica duplicada.
- Regras que não mudam: no máximo 3 rotas ativas (`MAX_ROTAS`), 10 buscas por execução, horários da
  tarefa agendada, pausa aleatória entre buscas, limite de 30 buscas avulsas sem confirmar (`LIMITE_SEM_CONFIRMAR`).
- Textos da interface em português do Brasil; datas no formato dd/mm/aaaa; valores em R$ como em `main.dinheiro`.

## 2. Como usar

- Rode `/continuar-etapa` (ou `/continuar-etapa N`). Ele detecta a próxima etapa pelos commits e a executa
  com o modelo e o esforço indicados.
- Uma sessão por etapa, de preferência nova.
- Cada etapa concluída vira um commit `Etapa N: <título>`. Esse prefixo é reservado para isso.
- O diário de execução fica em `progresso.md` (o que foi feito, desvios, problemas, verificação, pendências).

## 3. Skills e plugins

| Skill / plugin | Para quê | Etapas |
|---|---|---|
| `superpowers:test-driven-development` | escrever os testes antes da lógica (rotas, API) | 1, 2 |
| `headroom:peek` | ler o `logs\scanner.log` (até 1 MB) sem encher o contexto, para entender o formato | 2 |
| `anthropic-skills:frontend-design` | direção visual da interface (tipografia, cores, layout), para não ficar com cara de modelo pronto | 3, 4 |
| `dataviz` | gráfico de preços (forma, cores, eixos, legenda, tema claro/escuro) | 5 |
| `run` + `anthropic-skills:built-in-browser` | subir o servidor e conferir as telas no navegador embutido | 3, 4, 5, 6 |
| `security-review` | revisar o acesso pela rede local | 7 |
| `code-review`, `superpowers:verification-before-completion` | revisão final e conferência antes de declarar pronto | 8 |

Plugins padrão: o **Headroom** entra na Etapa 2. O **cartographer** não compensa: o projeto tem ~1.500
linhas e continuará pequeno. O **claude-code-setup** não tem papel neste plano.

## 4. Estrutura

```
scanner/
  rotas.py          NOVO: ler/gravar rotas no config.yaml (listar, adicionar, editar, pausar, retomar, remover)
  busca_avulsa.py   NOVO: a busca de scanner.buscar como função, com callback de progresso
  buscar.py         passa a usar rotas.py e busca_avulsa.py (só argparse, print e input)
  relatorio.py      ganha dados estruturados além do texto
  web/
    app.py          FastAPI: API JSON + arquivos estáticos
    tarefas.py      buscas e execuções em segundo plano (uma por vez), com progresso
    status.py       leitura do log, cota SerpApi, tarefa agendada do Windows
    static/         index.html, estilo.css, app.js (sem etapa de build, sem CDN)
Flight Scanner.cmd  abre o servidor (pythonw) e o navegador
tests/test_rotas.py, tests/test_web.py
```

API (rascunho; a Etapa 2 pode ajustar nomes):

- `GET /api/rotas`, `POST /api/rotas` (nova; com 3 ativas responde 409 e aceita `substituir`),
  `PUT /api/rotas` (editar, com o nome no corpo), `POST /api/rotas/acao` (`pausar|retomar|remover`).
  O nome da rota vai no corpo, porque tem `→` e espaços.
- `POST /api/busca` → `id`; `GET /api/busca/{id}` → progresso `[i/n]`, linhas e resultados.
- `GET /api/historico?rota=` (série do menor preço por busca e por combinação de datas), `GET /api/alertas`,
  `GET /api/relatorio`.
- `GET /api/status`; `POST /api/executar` (`dry_run`), via subprocesso `python -m scanner.main`;
  `POST /api/notificacao-teste`.

## 5. Etapas

### Etapa 1: Extrair a lógica de rotas e da busca avulsa
**Modelo:** Opus 5.5 · **Esforço:** medium · **Skills:** superpowers:test-driven-development
- Criar `scanner/rotas.py` com as funções hoje presas em `scanner/buscar.py` (`_blocos`, `_montar`, `_ativas`,
  `salvar_no_config`, `gerenciar`), sem `print`, `input` nem `SystemExit`: `listar()`, `adicionar(rota, substituir=None)`,
  `editar(nome_antigo, rota)`, `pausar(nome)`, `retomar(nome)`, `remover(nome)`. Erros viram exceções próprias
  (ex.: `RotaNaoEncontrada`, `NomeRepetido`, `VagasEsgotadas` com a lista das ativas).
- Preservar os comentários do `config.yaml` como hoje (edição por blocos de texto). Validar o YAML antes de gravar
  e gravar de forma atômica (arquivo temporário + `os.replace`), porque a tarefa agendada pode ler ao mesmo tempo.
  O caminho do config entra como parâmetro (padrão `CAMINHO_CONFIG`), para os testes usarem `tmp_path`.
- Criar `scanner/busca_avulsa.py` com o laço de busca de `buscar.main` como função:
  `buscar(rota, geral, reservas=0, progresso=callback) -> lista de Voo` (aplica filtros, `consultar_reservas`
  e o `preco_max` no fim, como hoje). O callback recebe `(i, n, texto)`.
- `scanner/buscar.py` passa a chamar essas funções; a saída e as perguntas no terminal ficam iguais.
- Escrever `tests/test_rotas.py` (adicionar, editar, pausar/retomar/remover, comentários preservados, limite de 3,
  substituição, nome repetido). Sem chamadas de rede nos testes.
- **Pronto quando:** `.\.venv\Scripts\python.exe -m pytest` passa (os testes antigos e os novos);
  `python -m scanner.buscar --listar` mostra o mesmo de antes; o `config.yaml` real continua igual byte a byte
  (o teste de ida e volta usa uma cópia dele).
- **Prompt para iniciar:** `Execute a Etapa 1 do plano.md.`

### Etapa 2: Servidor FastAPI e API
**Modelo:** Sonnet 5.5 · **Esforço:** medium · **Skills:** superpowers:test-driven-development, headroom:peek
- **Antes:** aprovar a instalação de `fastapi`, `uvicorn` e `httpx` (este último só para os testes) no `.venv`.
- Acrescentar as dependências ao `requirements.txt` com versão fixa.
- `scanner/web/app.py`: FastAPI com os endpoints da seção 4, servindo `scanner/web/static/` em `/`.
  Por enquanto, um `index.html` mínimo só para provar que serve.
- `scanner/web/tarefas.py`: busca avulsa em thread (uma por vez; uma segunda devolve 409), guardando progresso e
  resultados em memória; "Rodar agora" como subprocesso `python -m scanner.main [--dry-run]`, guardando a saída.
- `scanner/web/status.py`: últimas linhas `Início`/`Fim` e erros recentes do `logs\scanner.log` (ler só o fim do
  arquivo), uso da SerpApi no mês (`historico.serpapi_usadas`) e o limite do config, estado e próxima execução da
  tarefa agendada via `schtasks /query /fo csv /v`, procurando **FlightScanner e VooScanner** (a tarefa ao vivo
  ainda se chama VooScanner).
- `scanner/relatorio.py`: separar os cálculos numa função que devolve dados (por hora, por dia); `gerar()` continua
  devolvendo o mesmo texto.
- Histórico: consultas em `data\precos.db` com conexão própria por requisição (`historico.abrir`).
- Erros de `scanner.rotas` viram 404/409/422 com mensagem em português.
- `tests/test_web.py` com `TestClient`, usando config e banco temporários e `pesquisa.buscar` substituído por um falso.
- **Pronto quando:** `pytest` passa; `.\.venv\Scripts\python.exe -m uvicorn scanner.web.app:app --port 8765`
  sobe e `GET http://127.0.0.1:8765/api/rotas` e `/api/status` devolvem JSON com os dados reais.
- **Prompt para iniciar:** `Execute a Etapa 2 do plano.md.`

### Etapa 3: Base visual e telas "Buscas monitoradas" e "Status e ações"
**Modelo:** Sonnet 5.5 · **Esforço:** medium · **Skills:** anthropic-skills:frontend-design, run, anthropic-skills:built-in-browser
- Definir a direção visual com a skill `frontend-design` e registrá-la no topo do `estilo.css` (tokens de cor,
  tipografia, espaçamento), com tema claro e escuro (`prefers-color-scheme`).
- `index.html` + `app.js` (JavaScript puro, sem build): navegação entre as 4 telas por abas (`#buscar`, `#rotas`,
  `#historico`, `#status`); as telas ainda não feitas mostram "em breve".
- **Buscas monitoradas:** cartões com nome, rota, datas, passageiros, filtros, estado; "3 de 3 vagas" visível;
  pausar, retomar, remover (com confirmação) e editar (formulário). Ao mudar passageiros, avisar para trocar o
  nome (regra do README, para não misturar o histórico).
- **Status e ações:** última execução e resultado, erros recentes, cota SerpApi (usadas/limite), tarefa agendada
  (estado, próxima execução), botões "Rodar agora", "Rodar sem enviar (teste)" e "Testar notificação", com a
  saída aparecendo na página.
- Funciona em tela de celular (layout de uma coluna), mesmo que o acesso pelo celular só venha na Etapa 7.
- **Pronto quando:** no navegador embutido, em `http://127.0.0.1:8765`, pausar e retomar uma rota muda o
  `config.yaml` (conferir com `buscar --listar`); a tela de status mostra a cota e a tarefa agendada reais;
  "Rodar sem enviar" mostra a saída; sem erros no console do navegador.
- **Prompt para iniciar:** `Execute a Etapa 3 do plano.md.`

### Etapa 4: Tela "Buscar agora"
**Modelo:** Sonnet 5.5 · **Esforço:** medium · **Skills:** anthropic-skills:frontend-design, run, anthropic-skills:built-in-browser
- Formulário com os mesmos campos da CLI: origem, destino, intervalo de ida + passo, datas avulsas e pares
  ida/volta, durações, adultos/crianças/bebês, classe, preço máx., escalas máx., duração máx., reservas (SerpApi), top.
- Mostrar antes de buscar quantas combinações serão feitas; acima de 30, pedir confirmação explícita (equivalente ao `--forcar`).
- Durante a busca: barra de progresso `[i/n]` com as linhas de cada combinação (polling de `GET /api/busca/{id}`);
  o botão fica bloqueado enquanto há busca rodando.
- Resultados como tabela/cartões: preço total, datas e dias, escalas, duração, horário de saída, companhias,
  preço da agência quando houver, link "Abrir no Google Flights".
- "Monitorar esta busca": nome e queda %, chama `POST /api/rotas`; com 3 ativas, pergunta qual substituir (ou cancelar).
- **Pronto quando:** no navegador embutido, uma busca real pequena (1 data de ida, 1 duração) mostra progresso e
  resultados com link; "Monitorar" adiciona a rota ao `config.yaml` e ela aparece na tela de buscas monitoradas
  (depois, remover a rota de teste).
- **Prompt para iniciar:** `Execute a Etapa 4 do plano.md.`

### Etapa 5: Tela "Histórico e gráficos"
**Modelo:** Sonnet 5.5 · **Esforço:** medium · **Skills:** dataviz, run, anthropic-skills:built-in-browser
- Seletor de rota (inclusive as removidas que ainda têm dados no banco).
- Gráfico de linha do menor preço que passou nos filtros ao longo do tempo, com uma linha por combinação de datas
  (ou a melhor combinação destacada e as outras apagadas), linha do `preco_max` e marcação dos alertas enviados.
  Desenhado em SVG pelo próprio `app.js`, sem biblioteca externa, seguindo a skill `dataviz` (cores, eixos,
  dica ao passar o mouse, claro/escuro).
- Tabela "menor preço já visto por combinação de datas" e lista de alertas enviados.
- Relatório de horários (por hora e dia da semana) a partir de `GET /api/relatorio`, com aviso quando há poucos dados.
- **Pronto quando:** com o `data\precos.db` real, o gráfico da rota Rio → Recife aparece com as datas e os preços
  conferindo com uma consulta SQL direta ao banco; a dica mostra data, hora e preço; sem erros no console.
- **Prompt para iniciar:** `Execute a Etapa 5 do plano.md.`

### Etapa 6: Atalho de abertura e documentação
**Modelo:** Sonnet 5.5 · **Esforço:** low · **Skills:** run
- `Flight Scanner.cmd`: se o servidor já estiver no ar na porta 8765, só abre o navegador; senão, inicia com
  `pythonw -m uvicorn scanner.web.app:app --host 127.0.0.1 --port 8765` (sem janela de console) e abre o navegador.
  Botão "Desligar interface" na tela de status (encerra o servidor).
- README: seção "Interface gráfica" (como abrir, o que cada tela faz). Manter o `Fast scanner.cmd` da CLI.
- `CLAUDE.md`: comando para subir o servidor e onde ficam os arquivos da interface.
- **Pronto quando:** dar dois cliques no `Flight Scanner.cmd` abre a interface no navegador sem deixar janela de
  console; rodar de novo não abre um segundo servidor; "Desligar interface" encerra o processo.
- **Prompt para iniciar:** `Execute a Etapa 6 do plano.md.`

### Etapa 7 (opcional): Acesso pelo celular na rede Wi-Fi
**Modelo:** Opus 5.5 · **Esforço:** high · **Skills:** security-review
- **Antes:** o usuário decide se quer mesmo; o Windows vai pedir para liberar a porta no firewall (só rede privada).
- Opção `--rede` no atalho: escuta em `0.0.0.0` e exige um token aleatório (gerado e guardado no `.env`), passado
  uma vez pela URL e guardado em cookie `HttpOnly`; sem token, 401. Proteção contra CSRF nas ações que gravam.
- Tela de status mostra o endereço `http://<ip-local>:8765/?t=...` e um QR code (gerado sem serviço externo).
- **Pronto quando:** testes cobrem 401 sem token e acesso com token; abrindo pelo celular na mesma rede a interface
  funciona; `security-review` sem achados graves pendentes.
- **Prompt para iniciar:** `Execute a Etapa 7 do plano.md.`

### Etapa 8: Revisão final
**Modelo:** Opus 5.5 · **Esforço:** high · **Skills:** code-review, superpowers:verification-before-completion
- `/code-review` sobre tudo desde o commit do plano; corrigir o que for confirmado.
- Suíte de testes completa; conferir a CLI (`buscar --listar`, `main --dry-run`) e a interface (as 4 telas) de ponta a ponta.
- Conferir README, `CLAUDE.md` e `requirements.txt`.
- **Pronto quando:** `pytest` passa; `/code-review` sem achados confirmados em aberto; CLI e interface funcionam
  com o `config.yaml` e o banco reais.
- **Prompt para iniciar:** `Execute a Etapa 8 do plano.md.`

## 6. Verificação geral

- `.\.venv\Scripts\python.exe -m pytest` passa.
- A tarefa agendada continua rodando normalmente (`scanner.main` não muda de comportamento).
- CLI e interface dão o mesmo resultado para a mesma ação (ex.: pausar pela interface aparece em `buscar --listar`).
- O `config.yaml` mantém os comentários depois de qualquer edição pela interface.

## 7. Fora do escopo

- Login de usuários, hospedagem na internet, app de celular nativo.
- Mudar a frequência da tarefa agendada, o limite de buscas por execução ou o máximo de 3 rotas ativas.
- Instalar ou recriar a tarefa agendada pela interface (a tela de status só mostra o estado).
- Editar o `.env` (chaves e tópico do ntfy) pela interface.
