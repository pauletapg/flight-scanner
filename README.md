# Flight Scanner

Busca voos no Google Flights automaticamente, 12 vezes por dia, aplica os seus filtros
(preço, escalas, duração, datas flexíveis), guarda o histórico de preços e avisa no celular
quando aparece um voo bom ou quando o preço cai.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

## 1. Notificações no celular (ntfy)

O ntfy é um app gratuito de notificações, sem cadastro.

1. Instale o app **ntfy** (Play Store, App Store ou F-Droid).
2. No `.env`, `NTFY_TOPIC` tem o nome do seu canal (ex.: `flight-scanner-<código-aleatório>`).
   Não existe senha: quem souber o nome consegue ler as mensagens, por isso ele é aleatório.
   Não compartilhe.
3. No app, toque em **+** (Inscrever-se em um tópico), cole o nome do canal e confirme
   (servidor padrão `ntfy.sh`).
4. Teste:
   ```powershell
   .\.venv\Scripts\python.exe -m scanner.notificar --teste
   ```

Cada alerta chega como uma notificação: tocar abre o voo mais barato no Google Flights, e há um
botão para cada um dos 3 mais baratos. No Android, se as notificações atrasarem com a tela
apagada, desative a economia de bateria para o app ntfy.

Alternativa: WhatsApp pelo CallMeBot (https://www.callmebot.com/blog/free-api-whatsapp-messages/),
preenchendo `CALLMEBOT_PHONE` e `CALLMEBOT_APIKEY` e deixando `NTFY_TOPIC` vazio. É menos
confiável: o serviço fica fora do ar quando o WhatsApp bloqueia o número do bot.

Sem nenhuma configuração, o programa continua buscando e guardando o histórico. Os alertas
ficam registrados em `logs\scanner.log`.

## 2. Rotas e filtros

Edite o `config.yaml`. Em cada rota você define:

- `origem` e `destino`: códigos IATA dos aeroportos (GRU, CGH, GIG, LIS, MIA...). Se quiser o
  mesmo voo saindo de outro aeroporto, crie outra rota.
- **Datas**, de duas formas que podem ser usadas juntas:
  - `ida_entre: [início, fim]` + `passo_dias`: testa várias datas de ida num intervalo;
  - `datas:` lista de datas de ida (ex.: `- 2026-12-20`) ou de pares ida/volta fixos
    (ex.: `- [2026-12-22, 2027-01-05]`).
  - `duracoes_dias`: quantos dias de viagem testar para cada data de ida (sem essa linha, busca só ida).
- **Passageiros**: `adultos`, `criancas` (2 a 11 anos), `bebes_colo` (menores de 2 anos).
  O `preco_max` vale para o total de todos os passageiros.

Ao mudar os passageiros de uma rota, troque também o `nome` dela. Assim o histórico de preços
não mistura buscas de 1 pessoa com buscas de 4.

Cada rota vira várias buscas, uma por combinação de data de ida ×
duração da viagem. Com `max_buscas_por_execucao: 10`, cada execução faz 10 buscas e a
seguinte continua de onde a anterior parou. Assim o intervalo inteiro é coberto ao longo do dia.

**Quando chega um alerta** (no máximo uma mensagem por execução, com os 5 voos mais baratos):
- na primeira vez que um voo passa nos filtros para uma combinação de datas;
- depois disso, só se o preço cair pelo menos `queda_percentual` abaixo do menor preço já visto
  para essas datas.

## 3. Rodar

```powershell
# Uma execução, mostrando o alerta no terminal em vez de enviar
.\.venv\Scripts\python.exe -m scanner.main --dry-run

# Só uma rota
.\.venv\Scripts\python.exe -m scanner.main --dry-run --rota "São Paulo → Lisboa (novembro)"

# Execução normal (envia a notificação)
.\.venv\Scripts\python.exe -m scanner.main
```

## Busca pelo terminal

Para escolher os parâmetros na hora, sem editar o `config.yaml`:

```powershell
.\.venv\Scripts\python.exe -m scanner.buscar --origem RIO --destino REC `
    --ida-entre 20/12/2026 23/12/2026 --duracoes 6 7 8 `
    --adultos 2 --criancas 1 --escalas-max 1 --duracao-max 6 --preco-max 5000
```

- `--datas 22/12/2026 19/12/2026:27/12/2026`: datas de ida avulsas ou pares ida:volta fixos.
- `--salvar --nome "Minha viagem"`: depois da busca, adiciona a rota ao `config.yaml` para a
  tarefa agendada monitorar.
- `--help` lista todas as opções.

Mostra os melhores voos de cada combinação de datas, com o link do Google Flights.

## Interface gráfica

Tudo o que o `config.yaml` e o terminal fazem também dá para fazer numa página no navegador.
Dê dois cliques em **`Flight Scanner.cmd`**: se o servidor ainda não estiver no ar, ele sobe sem
deixar janela de console e abre `http://127.0.0.1:8765`. Rodar de novo só abre a página.
Por padrão a página só responde neste PC (para abrir no celular, veja "Acesso pelo celular" abaixo).
As buscas agendadas (seção 4) não dependem dela: rodam com a interface aberta ou não. O
`Fast scanner.cmd`, com a busca pelo terminal, continua como está.

- **Buscar agora**: a busca avulsa do terminal, com o progresso na tela, e depois "Monitorar esta
  busca" para guardar a rota no `config.yaml`. Antes de buscar, mostra quantas combinações de datas
  serão consultadas e pede confirmação acima de 30.
- **Monitoradas**: as rotas do `config.yaml` (no máximo 3 ativas) com datas, passageiros, filtros
  e queda para alertar; dá para editar, pausar, retomar e remover (o histórico de uma rota
  removida continua guardado).
- **Histórico**: gráfico do menor preço a cada busca, uma linha por combinação de datas, com o
  preço máximo da rota e os alertas enviados; tabela do menor preço já visto por combinação; e o
  relatório de horários (quais horas e dias da semana costumam ter preço mais baixo).
- **Status**: última execução, tarefa agendada, cota da SerpApi, avisos e erros recentes dos logs;
  os botões "Rodar agora", "Rodar sem enviar (teste)" e "Testar notificação"; e
  **Desligar interface**, que encerra o servidor.

Logs do servidor: `logs\interface.log`. Se o `Flight Scanner.cmd` avisar que a porta 8765 está em
uso por outro programa, feche-o e tente de novo. Para subir o servidor à mão, em outra porta:

```powershell
.\.venv\Scripts\python.exe -m uvicorn scanner.web.app:app --port 8766
```

### Acesso pelo celular (opcional)

Dê dois cliques em **`Flight Scanner (celular).cmd`** (é o `Flight Scanner.cmd --rede`). O servidor passa a
atender também o celular que estiver no mesmo Wi-Fi do PC, e a página abre na tela de status, em
**Acesso pelo celular**: ali está o endereço do PC na rede, `http://192.168.x.x:8765/?t=...`, com um botão
"Copiar". Mande o endereço para o celular (WhatsApp, e-mail) e abra-o lá **uma vez**: o celular guarda a
permissão num cookie e depois basta abrir `http://192.168.x.x:8765/`.

- **O token** (`t=...`) é uma senha aleatória, criada na primeira vez e guardada no `.env` como
  `INTERFACE_TOKEN`. Quem tiver o endereço controla a interface (edita as rotas, roda buscas, desliga):
  não o publique. Para trocar o token e desconectar os celulares, apague a linha `INTERFACE_TOKEN` do
  `.env` e abra o atalho de novo.
- **Firewall.** O Windows libera cada programa por perfil de rede (Privada ou Pública). O ideal é o Wi-Fi de
  casa marcado como "Privada" e o `pythonw.exe` do Python (o que criou o `.venv`) liberado só nela: se o aviso
  do firewall aparecer na primeira vez, marque só **Redes privadas**. Se o celular não abrir a página, o
  suspeito é o firewall: veja em Segurança do Windows → Firewall → Permitir um aplicativo se há regra de
  entrada para esse `pythonw.exe` **no perfil da rede em que o PC está agora** (Propriedades da rede Wi-Fi
  mostra se é Privada ou Pública). O PC e o celular precisam estar no mesmo Wi-Fi; alguns roteadores têm
  "isolamento de clientes", que impede um aparelho de falar com outro.
- **Mais de um endereço.** Com VPN, VirtualBox ou WSL o PC tem várias placas de rede. A tela de status
  mostra todas, a do Wi-Fi em geral primeiro; se o primeiro não abrir no celular, tente os outros.
- **Só em rede de confiança.** A conexão é HTTP, sem criptografia: quem estiver no mesmo Wi-Fi e capturar o
  tráfego enxerga o token. Use no Wi-Fi de casa, nunca em rede pública ou de hotel.
- **O PC não precisa do token**: o navegador do próprio PC (`127.0.0.1`) entra direto. Sem `--rede` o
  servidor só atende o PC e recusa qualquer outro aparelho, mesmo que o uvicorn seja subido à mão em
  `0.0.0.0`. Para voltar a esse modo: "Desligar interface" e abra o `Flight Scanner.cmd` normal.
- Se a interface já estiver aberta sem o acesso pelo celular, o atalho `--rede` avisa e pede para desligá-la antes.

## 4. Agendamento automático

```powershell
powershell -ExecutionPolicy Bypass -File instalar_tarefa.ps1
```

Cria a tarefa `FlightScanner`, que roda nas horas ímpares (01h, 03h, ..., 23h), com até 20 min de
atraso aleatório. Se o PC estiver desligado num horário, a execução roda quando ele ligar.
Para mudar os horários: `instalar_tarefa.ps1 -Horarios 7,13,19`.
Para remover: `Unregister-ScheduledTask -TaskName FlightScanner`.

## Preço das agências (SerpApi)

Na página de reserva do Google, agências como a Zupper costumam vender ~10% mais barato que a
companhia, mas esse preço não aparece na lista de voos. Com a SerpApi o scanner consulta essas
"Opções de reserva":

1. Crie uma conta em https://serpapi.com (250 buscas/mês grátis) e copie a API key.
2. Coloque em `SERPAPI_KEY` no `.env`.

Cada consulta gasta 3 buscas da SerpApi (ida, volta e reserva). Para caber no plano grátis:
- só consulta o voo mais barato que esteja até `margem_percentual` acima do `preco_max`;
- no máximo `consultas_reserva_por_execucao` por execução, e o `limite_mensal` é dividido
  igualmente pelos dias (240/mês ≈ 8 buscas ≈ 2 consultas por dia);
- se o preço da lista não mudou, reaproveita a consulta anterior sem gastar nada.

O `preco_max` vale para o menor preço entre a lista e as agências. No terminal, use
`--reservas 3` no `scanner.buscar` para consultar os 3 mais baratos.

## 5. Quais horários têm preços mais baixos?

```powershell
.\.venv\Scripts\python.exe -m scanner.relatorio
```

Compara cada busca com o preço médio da mesma combinação de datas e mostra, por hora do dia
e por dia da semana, se os preços encontrados estavam acima ou abaixo da média. Vale a pena
olhar depois de 2 a 3 semanas de coleta.

## Se algo parar de funcionar

- O `fast-flights` não é oficial. Se o Google mudar a página, as buscas falham e o erro
  aparece em `logs\scanner.log`. Primeiro tente `pip install -U fast-flights` e rode os testes:
  o `scanner\pesquisa.py` usa funções internas dele para ler as duas listas de voos do Google.
- Quando o Google Flights falha e há `SERPAPI_KEY`, o programa usa a SerpApi no lugar.
- Arquivos: histórico em `data\precos.db` (SQLite), log em `logs\scanner.log`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```
