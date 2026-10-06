// Flight Scanner: interface (JavaScript puro, sem build). Conversa com a API em /api (scanner/web/app.py).
"use strict";

// --- utilidades -------------------------------------------------------------------------------------------

/** Cria um elemento: h("p", {class: "x"}, "texto", outroElemento). Texto sempre como texto (sem innerHTML). */
function h(tag, atributos, ...filhos) {
  const elemento = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (nome.startsWith("on")) elemento.addEventListener(nome.slice(2), valor);
    else elemento.setAttribute(nome, valor === true ? "" : valor);
  }
  for (const filho of filhos.flat()) {
    if (filho === null || filho === undefined || filho === false) continue;
    elemento.append(filho instanceof Node ? filho : String(filho));
  }
  return elemento;
}

/** Chama a API; em erro, lança Error com a mensagem do {"detail": ...} e os dados extras em .dados. */
async function api(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    throw new Error("Sem resposta do servidor. Ele ainda está aberto?");
  }
  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    const erro = new Error((dados && dados.detail) || `O servidor respondeu ${resposta.status}.`);
    erro.status = resposta.status;
    erro.dados = dados;
    throw erro;
  }
  return dados;
}

/** "2026-12-20" → "20/12/2026". */
function data(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

/** "2026-10-05T19:45:28" → "05/10/2026 às 19:45". */
function dataHora(iso) {
  if (!iso) return "";
  return `${data(iso)} às ${iso.slice(11, 16)}`;
}

/** Como main.dinheiro: "R$ 5.000". */
function dinheiro(valor) {
  return "R$ " + String(Math.round(valor)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function plural(n, singular, varios) {
  return `${n} ${n === 1 ? singular : varios}`;
}

function avisar(texto, tipo = "ok") {
  const toast = h("div", { class: `toast ${tipo}`, role: tipo === "erro" ? "alert" : "status" }, texto);
  document.getElementById("avisos").append(toast);
  setTimeout(() => toast.remove(), tipo === "erro" ? 9000 : 4500);
}

/** Diálogo de confirmação; devolve true se a pessoa confirmou. `perigo` pinta o botão de vermelho.
 * A resposta vem do submit (síncrono), não do evento "close", que o navegador pode atrasar. */
function confirmar(titulo, texto, botao, { perigo = false } = {}) {
  const dialogo = document.getElementById("dialogo-confirmar");
  const form = dialogo.querySelector("form");
  const confirma = document.getElementById("botao-confirmar");
  document.getElementById("titulo-confirmar").textContent = titulo;
  document.getElementById("texto-confirmar").textContent = texto;
  confirma.textContent = botao;
  confirma.classList.toggle("perigo-cheio", perigo);
  dialogo.showModal();
  return new Promise((resolver) => {
    const terminar = (resposta) => {
      form.removeEventListener("submit", aoEnviar);
      dialogo.removeEventListener("cancel", aoCancelar);
      if (dialogo.open) dialogo.close();
      resolver(resposta);
    };
    const aoEnviar = (evento) => {
      evento.preventDefault();
      terminar(Boolean(evento.submitter && evento.submitter.value === "sim"));
    };
    const aoCancelar = (evento) => {
      evento.preventDefault();
      terminar(false);
    };
    form.addEventListener("submit", aoEnviar);
    dialogo.addEventListener("cancel", aoCancelar); // tecla Esc
  });
}

/** Desabilita o botão enquanto a ação roda. */
async function comBotao(botao, acao) {
  botao.disabled = true;
  try {
    return await acao();
  } finally {
    botao.disabled = false;
  }
}

// --- navegação --------------------------------------------------------------------------------------------

const TELAS = {
  buscar: null,
  rotas: () => carregarRotas(),
  historico: null,
  status: () => carregarStatus(),
};
const TELA_INICIAL = "rotas"; // enquanto "Buscar agora" não existe (Etapa 4)

function mostrarTela() {
  const nome = location.hash.slice(1) in TELAS ? location.hash.slice(1) : TELA_INICIAL;
  for (const secao of document.querySelectorAll(".tela")) secao.hidden = secao.id !== `tela-${nome}`;
  for (const aba of document.querySelectorAll(".abas a")) {
    if (aba.dataset.tela === nome) aba.setAttribute("aria-current", "page");
    else aba.removeAttribute("aria-current");
  }
  if (nome !== "status") pararAcompanhamento();
  if (TELAS[nome]) TELAS[nome]();
}

// --- buscas monitoradas -----------------------------------------------------------------------------------

const CLASSES = {
  economy: "Econômica",
  "premium-economy": "Econômica premium",
  business: "Executiva",
  first: "Primeira classe",
};

let rotasAtuais = [];

function textoIda(rota) {
  const partes = [];
  if (rota.ida_entre) {
    const [inicio, fim] = rota.ida_entre;
    const passo = rota.passo_dias || 1;
    partes.push(`${data(inicio)} a ${data(fim)}, ${passo === 1 ? "todo dia" : `a cada ${passo} dias`}`);
  }
  for (const d of rota.datas || []) {
    partes.push(Array.isArray(d) ? `${data(d[0])} → ${data(d[1])} (ida e volta)` : data(d));
  }
  return partes;
}

function textoPassageiros(rota) {
  const partes = [plural(rota.adultos || 1, "adulto", "adultos")];
  if (rota.criancas) partes.push(plural(rota.criancas, "criança", "crianças"));
  if (rota.bebes_colo) partes.push(plural(rota.bebes_colo, "bebê de colo", "bebês de colo"));
  return partes.join(", ");
}

function textoFiltros(rota) {
  const f = rota.filtros || {};
  const partes = [];
  if (f.preco_max) partes.push(`até ${dinheiro(f.preco_max)} no total`);
  if (f.escalas_max === 0) partes.push("só voo direto");
  else if (f.escalas_max) partes.push(`até ${plural(f.escalas_max, "escala", "escalas")}`);
  if (f.duracao_max_horas) partes.push(`até ${String(f.duracao_max_horas).replace(".", ",")} h de voo`);
  return partes.length ? partes.join(" · ") : "nenhum";
}

function campo(rotulo, ...valor) {
  return h("div", null, h("dt", null, rotulo), h("dd", null, ...valor));
}

function fita(rota) {
  const pausada = rota.pausada;
  const ida = textoIda(rota);
  const duracoes = rota.duracoes_dias && rota.duracoes_dias.length
    ? `${rota.duracoes_dias.join(", ")} dias`
    : "só ida";
  return h("article", { class: `fita${pausada ? " pausada" : ""}`, "aria-label": rota.nome },
    h("div", { class: "fita-id" },
      h("div", { class: "fita-codigos" }, rota.origem, h("span", { class: "seta", "aria-hidden": "true" }, "›"),
        h("span", { class: "sr" }, " para "), rota.destino),
      h("div", { class: "fita-nome" }, rota.nome),
      h("span", { class: "estado" }, pausada ? "Pausada" : "Monitorando"),
    ),
    h("dl", { class: "fita-campos" },
      campo("Ida", ...ida.flatMap((t, i) => (i ? [h("br"), t] : [t]))),
      campo("Duração", duracoes),
      campo("Passageiros", textoPassageiros(rota)),
      campo("Classe", CLASSES[rota.classe] || rota.classe || "Econômica"),
      campo("Filtros", textoFiltros(rota)),
      campo("Alerta", `queda de ${String((rota.alerta || {}).queda_percentual ?? 10).replace(".", ",")}%`),
    ),
    h("div", { class: "fita-acoes" },
      pausada
        ? h("button", { type: "button", class: "botao primario", onclick: (e) => acaoRota(e.currentTarget, rota, "retomar") }, "Retomar")
        : h("button", { type: "button", class: "botao", onclick: (e) => acaoRota(e.currentTarget, rota, "pausar") }, "Pausar"),
      h("button", { type: "button", class: "botao", onclick: () => abrirEdicao(rota) }, "Editar"),
      h("button", { type: "button", class: "botao perigo", onclick: (e) => removerRota(e.currentTarget, rota) }, "Remover"),
    ),
  );
}

function desenharVagas(ativas, maximo) {
  const slots = h("span", { class: "slots", "aria-hidden": "true" },
    Array.from({ length: maximo }, (_, i) => h("span", { class: `slot${i < ativas ? " ocupada" : ""}` })));
  document.getElementById("vagas").replaceChildren(
    slots, h("span", null, h("b", null, `${ativas} de ${maximo}`), " vagas em uso"));
}

async function carregarRotas() {
  const lista = document.getElementById("lista-rotas");
  try {
    const dados = await api("GET", "/api/rotas");
    rotasAtuais = dados.rotas;
    desenharVagas(dados.ativas, dados.max_ativas);
    if (!dados.rotas.length) {
      lista.replaceChildren(h("p", { class: "vazio" },
        "Nenhuma rota monitorada. Para criar uma, faça uma busca e use \"Monitorar esta busca\" ",
        "(ou, no terminal, python -m scanner.buscar ... --salvar)."));
      return;
    }
    // Ativas primeiro, na ordem do config.yaml.
    const ordenadas = [...dados.rotas].sort((a, b) => Number(a.pausada) - Number(b.pausada));
    lista.replaceChildren(...ordenadas.map(fita));
  } catch (erro) {
    lista.replaceChildren(h("p", { class: "erro-form" }, `Não consegui ler as rotas: ${erro.message}`));
  }
}

async function acaoRota(botao, rota, acao) {
  await comBotao(botao, async () => {
    try {
      await api("POST", "/api/rotas/acao", { nome: rota.nome, acao });
      avisar(acao === "pausar" ? `Rota pausada: ${rota.nome}` : `Rota retomada: ${rota.nome}`);
    } catch (erro) {
      avisar(erro.status === 409 && erro.dados && erro.dados.ativas
        ? `${erro.message} Pause uma das ativas antes de retomar esta.`
        : erro.message, "erro");
    }
  });
  carregarRotas();
}

async function removerRota(botao, rota) {
  const ok = await confirmar("Remover rota",
    `Remover "${rota.nome}" do monitoramento? O histórico de preços dela continua guardado.`, "Remover rota",
    { perigo: true });
  if (!ok) return;
  await comBotao(botao, async () => {
    try {
      await api("POST", "/api/rotas/acao", { nome: rota.nome, acao: "remover" });
      avisar(`Rota removida: ${rota.nome}`);
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  });
  carregarRotas();
}

// --- formulário de rota (edição; a Etapa 4 reaproveita lerFormularioRota) ---------------------------------

let rotaEmEdicao = null;

/** "20/12/2026" → "2026-12-20"; aceita também "2026-12-20". Devolve null se não for data. */
function isoDeTexto(texto) {
  const t = texto.trim();
  let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? t : null;
}

function preencherFormularioRota(form, rota) {
  const f = rota.filtros || {};
  const valores = {
    nome: rota.nome,
    origem: rota.origem,
    destino: rota.destino,
    ida_inicio: rota.ida_entre ? rota.ida_entre[0] : "",
    ida_fim: rota.ida_entre ? rota.ida_entre[1] : "",
    passo_dias: rota.passo_dias || 1,
    datas: (rota.datas || []).map((d) => (Array.isArray(d) ? `${data(d[0])} a ${data(d[1])}` : data(d))).join("\n"),
    duracoes_dias: (rota.duracoes_dias || []).join(", "),
    adultos: rota.adultos ?? 1,
    criancas: rota.criancas ?? 0,
    bebes_colo: rota.bebes_colo ?? 0,
    classe: rota.classe || "economy",
    preco_max: f.preco_max ?? "",
    escalas_max: f.escalas_max ?? "",
    duracao_max_horas: f.duracao_max_horas ?? "",
    queda_percentual: (rota.alerta || {}).queda_percentual ?? 10,
  };
  for (const [nome, valor] of Object.entries(valores)) form.elements[nome].value = valor;
}

/** Lê o formulário no formato de RotaEntrada da API. Lança Error com mensagem para a pessoa. */
function lerFormularioRota(form) {
  const v = (nome) => form.elements[nome].value.trim();
  const numero = (nome) => (v(nome) === "" ? null : Number(v(nome)));
  const rota = {
    nome: v("nome") || null,
    origem: v("origem").toUpperCase(),
    destino: v("destino").toUpperCase(),
    adultos: numero("adultos") ?? 1,
    criancas: numero("criancas") ?? 0,
    bebes_colo: numero("bebes_colo") ?? 0,
    classe: v("classe"),
    filtros: {},
    alerta: { queda_percentual: numero("queda_percentual") ?? 10 },
  };
  if (rota.origem.length !== 3 || rota.destino.length !== 3) {
    throw new Error("Origem e destino são códigos de aeroporto com 3 letras (ex.: GRU, REC).");
  }
  if (v("ida_inicio") || v("ida_fim")) {
    if (!v("ida_inicio") || !v("ida_fim")) throw new Error("Preencha as duas pontas do intervalo de ida (de e até).");
    if (v("ida_fim") < v("ida_inicio")) throw new Error("No intervalo de ida, a data \"até\" vem antes da \"de\".");
    rota.ida_entre = [v("ida_inicio"), v("ida_fim")];
    rota.passo_dias = numero("passo_dias") ?? 1;
  }
  const datas = [];
  for (const linha of v("datas").split("\n").map((l) => l.trim()).filter(Boolean)) {
    const partes = linha.split(/\s+a\s+|\s*→\s*/);
    const isos = partes.map(isoDeTexto);
    if (isos.some((d) => !d) || isos.length > 2) {
      throw new Error(`Não entendi a data "${linha}". Use dd/mm/aaaa ou "dd/mm/aaaa a dd/mm/aaaa".`);
    }
    datas.push(isos.length === 2 ? isos : isos[0]);
  }
  if (datas.length) rota.datas = datas;
  if (!rota.ida_entre && !rota.datas) throw new Error("Informe as datas de ida: um intervalo e/ou datas avulsas.");
  if (v("duracoes_dias")) {
    const duracoes = v("duracoes_dias").split(/[\s,;]+/).filter(Boolean).map(Number);
    if (duracoes.some((d) => !Number.isInteger(d) || d < 1)) {
      throw new Error("Duração da viagem: use números inteiros de dias, separados por vírgula (ex.: 6, 7, 8).");
    }
    rota.duracoes_dias = duracoes;
  }
  for (const nome of ["preco_max", "escalas_max", "duracao_max_horas"]) {
    if (numero(nome) !== null) rota.filtros[nome] = numero(nome);
  }
  return rota;
}

function passageirosDoFormulario(form) {
  return ["adultos", "criancas", "bebes_colo"].map((n) => Number(form.elements[n].value || 0)).join("/");
}

function atualizarAvisoPassageiros() {
  const form = document.getElementById("form-rota");
  const original = rotaEmEdicao;
  if (!original) return;
  const antes = [original.adultos ?? 1, original.criancas ?? 0, original.bebes_colo ?? 0].join("/");
  const mudouPassageiros = passageirosDoFormulario(form) !== antes;
  const mesmoNome = form.elements.nome.value.trim() === original.nome;
  document.getElementById("aviso-passageiros").hidden = !(mudouPassageiros && mesmoNome);
}

function abrirEdicao(rota) {
  rotaEmEdicao = rota;
  const form = document.getElementById("form-rota");
  preencherFormularioRota(form, rota);
  document.getElementById("erro-editar").hidden = true;
  atualizarAvisoPassageiros();
  document.getElementById("dialogo-editar").showModal();
}

async function salvarEdicao(evento) {
  evento.preventDefault();
  const form = evento.currentTarget;
  const erroForm = document.getElementById("erro-editar");
  erroForm.hidden = true;
  let rota;
  try {
    rota = lerFormularioRota(form);
  } catch (erro) {
    erroForm.textContent = erro.message;
    erroForm.hidden = false;
    return;
  }
  const botao = form.querySelector('[type="submit"]');
  await comBotao(botao, async () => {
    try {
      const resposta = await api("PUT", "/api/rotas", { nome: rotaEmEdicao.nome, rota });
      document.getElementById("dialogo-editar").close();
      avisar(`Rota salva: ${resposta.nome}`);
      carregarRotas();
    } catch (erro) {
      erroForm.textContent = erro.message;
      erroForm.hidden = false;
    }
  });
}

// --- status e ações ---------------------------------------------------------------------------------------

let acompanhamento = null;

function pararAcompanhamento() {
  clearTimeout(acompanhamento);
  acompanhamento = null;
}

function quadroExecucao(ultima) {
  if (!ultima) return [h("p", { class: "secundario" }, "Nenhuma execução no log recente.")];
  const terminou = Boolean(ultima.fim);
  const fimTexto = (ultima.fim_texto || "").replace(/^Fim:\s*/, "");
  return [
    h("div", { class: "destaque" }, dataHora(ultima.inicio)),
    h("div", null, (ultima.inicio_texto || "").replace(/^Início:\s*/, "")),
    terminou
      ? h("div", null, h("span", { class: "ok" }, "Terminou "), h("span", { class: "hora" }, ultima.fim.slice(11, 16)),
        fimTexto ? ` · ${fimTexto}` : "")
      : h("div", { class: "atencao" }, "Sem registro de fim: está rodando agora ou foi interrompida."),
  ];
}

function quadroTarefa(tarefas, erroTarefas) {
  if (erroTarefas) return [h("p", { class: "ruim" }, erroTarefas)];
  if (!tarefas.length) {
    return [h("p", { class: "atencao" }, "Nenhuma tarefa agendada encontrada (FlightScanner ou VooScanner). ",
      "Para instalar, rode instalar_tarefa.ps1.")];
  }
  return tarefas.map((t) => {
    const habilitada = !/desabilit|disabled/i.test(t.situacao || "");
    const resultadoOk = t.ultimo_resultado === "0";
    return h("div", { class: "corpo" },
      h("div", { class: "destaque" }, t.proxima ? dataHora(t.proxima) : "Sem próxima execução"),
      h("div", { class: "secundario" }, "próxima execução"),
      h("div", null, h("span", { class: habilitada ? "ok" : "ruim" }, habilitada ? "Habilitada" : "Desabilitada"),
        ` · ${t.status} · tarefa ${t.nome}`),
      t.ultima ? h("div", { class: "secundario" }, `Última: ${dataHora(t.ultima)} · `,
        h("span", { class: resultadoOk ? "ok" : "ruim" }, resultadoOk ? "terminou bem" : `código ${t.ultimo_resultado}`)) : null,
    );
  });
}

function quadroSerpapi(s) {
  const fracao = s.limite_mensal ? Math.min(1, s.usadas_mes / s.limite_mensal) : 0;
  return [
    h("div", { class: "destaque" }, `${s.usadas_mes} de ${s.limite_mensal}`),
    h("div", { class: `medidor${fracao >= 0.9 ? " cheio" : ""}`, role: "meter", "aria-valuemin": 0,
      "aria-valuemax": s.limite_mensal, "aria-valuenow": s.usadas_mes, "aria-label": "Consultas usadas no mês" },
      h("span", { style: `width: ${(fracao * 100).toFixed(1)}%` })),
    h("div", { class: "secundario" }, `consultas usadas este mês · ${s.usadas_hoje} hoje`),
  ];
}

function desenharErros(erros) {
  const lista = document.getElementById("lista-erros");
  if (!erros.length) {
    lista.replaceChildren(h("li", { class: "secundario" }, "Nenhum aviso ou erro no log recente."));
    return;
  }
  const NIVEIS = { WARNING: "Aviso", ERROR: "Erro", CRITICAL: "Crítico" };
  lista.replaceChildren(...erros.map((e) => {
    // Alguns avisos trazem o alerta inteiro (vários KB): mostra a primeira linha e o resto sob demanda.
    const [primeira, ...resto] = e.mensagem.split("\n");
    const texto = resto.length
      ? h("details", null, h("summary", null, primeira), h("pre", { class: "console" }, resto.join("\n")))
      : h("span", { class: "sem-detalhe" }, primeira);
    return h("li", null,
      h("span", { class: "hora" }, dataHora(e.quando)),
      h("span", { class: `nivel ${e.nivel}` }, NIVEIS[e.nivel] || e.nivel),
      texto);
  }));
}

function desenharExecucao(execucao) {
  const area = document.getElementById("saida-execucao");
  const botoes = [document.getElementById("rodar-agora"), document.getElementById("rodar-teste")];
  const rodando = execucao && execucao.estado === "rodando";
  for (const b of botoes) b.disabled = rodando;
  if (!execucao) {
    area.replaceChildren();
    return;
  }
  const tipo = execucao.dry_run ? "Rodar sem enviar (teste)" : "Rodar agora";
  let titulo;
  if (rodando) titulo = h("span", { class: "rodando" }, `${tipo}: rodando desde ${execucao.inicio.slice(11, 16)}…`);
  else if (execucao.estado === "concluida") titulo = h("span", null, `${tipo}: `, h("span", { class: "ok" }, "concluída"), ` às ${execucao.fim.slice(11, 16)}`);
  else titulo = h("span", null, `${tipo}: `, h("span", { class: "ruim" }, `terminou com erro${execucao.codigo !== null ? ` (código ${execucao.codigo})` : ""}`), ` às ${(execucao.fim || "").slice(11, 16)}`);
  area.replaceChildren(h("div", { class: "saida" },
    h("div", { class: "saida-titulo" }, titulo),
    rodando ? null : h("pre", { class: "console" }, (execucao.saida || "(sem saída)").replace(/\r/g, ""))));
}

async function carregarStatus() {
  pararAcompanhamento();
  const corpos = ["execucao", "tarefa", "serpapi"].map((n) => document.querySelector(`#quadro-${n} .corpo`));
  let s;
  try {
    s = await api("GET", "/api/status");
  } catch (erro) {
    corpos[0].replaceChildren(h("p", { class: "ruim" }, `Não consegui ler o status: ${erro.message}`));
    return;
  }
  corpos[0].replaceChildren(...quadroExecucao(s.ultima_execucao));
  corpos[1].replaceChildren(...quadroTarefa(s.tarefas, s.erro_tarefas));
  corpos[2].replaceChildren(...quadroSerpapi(s.serpapi));
  desenharErros(s.erros);
  desenharExecucao(s.execucao);
  desenharProxima(s.tarefas);
  if (s.execucao && s.execucao.estado === "rodando") acompanharExecucao();
}

/** Enquanto o "Rodar agora" estiver rodando, consulta a cada 3 s; ao terminar, recarrega o status. */
function acompanharExecucao() {
  pararAcompanhamento();
  acompanhamento = setTimeout(async () => {
    try {
      const execucao = await api("GET", "/api/executar");
      if (execucao && execucao.estado === "rodando") {
        desenharExecucao(execucao);
        acompanharExecucao();
      } else {
        avisar(execucao && execucao.estado === "concluida" ? "Execução concluída." : "A execução terminou com erro.",
          execucao && execucao.estado === "concluida" ? "ok" : "erro");
        carregarStatus();
      }
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }, 3000);
}

async function executar(dryRun) {
  if (!dryRun) {
    const ok = await confirmar("Rodar agora",
      "Faz até 10 buscas no Google Flights agora, como a tarefa agendada, e envia o alerta no celular se encontrar voo bom.",
      "Rodar agora");
    if (!ok) return;
  }
  try {
    const execucao = await api("POST", "/api/executar", { dry_run: dryRun });
    desenharExecucao(execucao);
    acompanharExecucao();
  } catch (erro) {
    avisar(erro.message, "erro");
  }
}

async function testarNotificacao(evento) {
  await comBotao(evento.currentTarget, async () => {
    try {
      await api("POST", "/api/notificacao-teste");
      avisar("Notificação de teste enviada. Confira o celular.");
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  });
}

// --- topo: próxima execução agendada ----------------------------------------------------------------------

function desenharProxima(tarefas) {
  const alvo = document.getElementById("proxima");
  const proximas = (tarefas || []).map((t) => t.proxima).filter(Boolean).sort();
  if (!proximas.length) {
    alvo.hidden = true;
    return;
  }
  const quando = proximas[0];
  const agora = new Date();
  const hojeIso = [agora.getFullYear(), agora.getMonth() + 1, agora.getDate()].map((n) => String(n).padStart(2, "0")).join("-");
  const hoje = hojeIso === quando.slice(0, 10);
  alvo.replaceChildren("Próxima busca agendada: ", h("b", null, hoje ? `hoje, ${quando.slice(11, 16)}` : dataHora(quando)));
  alvo.hidden = false;
}

// --- início -----------------------------------------------------------------------------------------------

document.getElementById("form-rota").addEventListener("submit", salvarEdicao);
document.getElementById("form-rota").addEventListener("input", atualizarAvisoPassageiros);
document.querySelector("#dialogo-editar [data-fechar]").addEventListener("click", () => document.getElementById("dialogo-editar").close());
document.getElementById("atualizar-status").addEventListener("click", carregarStatus);
document.getElementById("rodar-agora").addEventListener("click", () => executar(false));
document.getElementById("rodar-teste").addEventListener("click", () => executar(true));
document.getElementById("testar-notificacao").addEventListener("click", testarNotificacao);
window.addEventListener("hashchange", mostrarTela);

mostrarTela();
if (location.hash.slice(1) !== "status") {
  api("GET", "/api/status").then((s) => desenharProxima(s.tarefas)).catch(() => {});
}
