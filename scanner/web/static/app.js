// Flight Scanner: interface (JavaScript puro, sem build). Conversa com a API em /api (scanner/web/app.py).
"use strict";

// --- utilidades -------------------------------------------------------------------------------------------

/** Cria um elemento: h("p", {class: "x"}, "texto", outroElemento). Texto sempre como texto (sem innerHTML). */
function h(tag, atributos, ...filhos) {
  return preencher(document.createElement(tag), atributos, filhos);
}

/** Como h(), para elementos SVG (gráficos). */
function s(tag, atributos, ...filhos) {
  return preencher(document.createElementNS("http://www.w3.org/2000/svg", tag), atributos, filhos);
}

function preencher(elemento, atributos, filhos) {
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

/** Chama a API; em erro, lança Error com a mensagem do {"detail": ...} e os dados extras em .dados.
 * O cabeçalho X-Flight-Scanner vai em toda chamada: o servidor só aceita ações que gravam vindas desta página
 * (um site de fora não consegue mandar cabeçalho próprio sem a permissão do navegador). */
async function api(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: { "X-Flight-Scanner": "1" } };
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

/** Abre o diálogo e espera: devolve `aoConfirmar()` se a pessoa usou o botão value="sim", ou null se cancelou
 * (outro botão ou Esc). A resposta vem do submit (síncrono), não do evento "close", que o navegador pode atrasar. */
function esperarResposta(dialogo, aoConfirmar) {
  const form = dialogo.querySelector("form");
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
      terminar(evento.submitter && evento.submitter.value === "sim" ? aoConfirmar() : null);
    };
    const aoCancelar = (evento) => {
      evento.preventDefault();
      terminar(null);
    };
    form.addEventListener("submit", aoEnviar);
    dialogo.addEventListener("cancel", aoCancelar); // tecla Esc
  });
}

/** Diálogo de confirmação; devolve true se a pessoa confirmou. `perigo` pinta o botão de vermelho. */
async function confirmar(titulo, texto, botao, { perigo = false } = {}) {
  const confirma = document.getElementById("botao-confirmar");
  document.getElementById("titulo-confirmar").textContent = titulo;
  document.getElementById("texto-confirmar").textContent = texto;
  confirma.textContent = botao;
  confirma.classList.toggle("perigo-cheio", perigo);
  return (await esperarResposta(document.getElementById("dialogo-confirmar"), () => true)) === true;
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
  buscar: () => carregarBusca(),
  rotas: () => carregarRotas(),
  historico: () => carregarHistorico(),
  status: () => carregarStatus(),
};
const TELA_INICIAL = "buscar";

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

// --- formulário de rota (edição e "Buscar agora": os campos comuns vêm do <template id="campos-rota">) ------

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
  for (const [nome, valor] of Object.entries(valores)) {
    if (form.elements[nome]) form.elements[nome].value = valor; // a busca não tem nome nem queda %
  }
}

/** Lê o formulário no formato de RotaEntrada da API. Lança Error com mensagem para a pessoa. */
function lerFormularioRota(form) {
  const v = (nome) => (form.elements[nome] ? form.elements[nome].value.trim() : "");
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
  form.querySelector(".aviso-passageiros").hidden = !(mudouPassageiros && mesmoNome);
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

// --- buscar agora -----------------------------------------------------------------------------------------

let buscaAtual = null; // último estado de GET /api/busca/{id}; config = a rota no formato do config.yaml
let acompanhamentoBusca = null;
let previaTimer = null;
let previaPedida = 0; // descarta respostas da prévia que chegam fora de ordem
let formBuscaMexido = false; // depois que a pessoa mexe, a página não refaz o formulário com a última busca
let todosResultados = false;

function mostrarErro(alvo, texto) {
  alvo.textContent = texto;
  alvo.hidden = false;
}

/** "2026-12-20" → "sáb 20/12". */
function diaCurto(iso) {
  const semana = new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return `${semana} ${data(iso).slice(0, 5)}`;
}

function diasEntre(inicio, fim) {
  const meioDia = (iso) => new Date(`${iso.slice(0, 10)}T12:00:00`);
  return Math.round((meioDia(fim) - meioDia(inicio)) / 86400000);
}

function textoDatasVoo(v) {
  if (!v.volta) return `${diaCurto(v.ida)} (só ida)`;
  return `${diaCurto(v.ida)} → ${diaCurto(v.volta)} · ${plural(diasEntre(v.ida, v.volta), "dia", "dias")}`;
}

function textoDuracao(minutos) {
  return `${Math.floor(minutos / 60)}h${String(minutos % 60).padStart(2, "0")}`;
}

/** Resultado de cada combinação, pelo texto que busca_avulsa.buscar manda no progresso:
 * "...: falhou (motivo)", "...: N voo(s), nenhum nos filtros" ou "...: N voo(s), melhor R$ X". */
function tipoLinha(texto) {
  if (/: falhou \(/.test(texto)) return "falhou";
  if (/nenhum nos filtros$/.test(texto)) return "vazia";
  return "achou";
}

function desenharProgresso(busca) {
  const rodando = busca.estado === "rodando";
  const tipos = new Map(busca.linhas.filter((l) => l.i !== null).map((l) => [l.i, tipoLinha(l.texto)]));
  const regua = document.getElementById("regua-busca");
  regua.replaceChildren(...Array.from({ length: busca.n }, (_, k) => {
    const tipo = tipos.get(k + 1);
    const agora = rodando && !tipo && k === busca.i; // a combinação que está sendo buscada
    return h("span", { class: `casa${tipo ? ` ${tipo}` : ""}${agora ? " agora" : ""}` });
  }));
  regua.setAttribute("aria-valuemin", "0");
  regua.setAttribute("aria-valuemax", String(busca.n));
  regua.setAttribute("aria-valuenow", String(busca.i));
  regua.setAttribute("aria-valuetext", `${busca.i} de ${busca.n} buscas feitas`);

  const titulo = document.getElementById("titulo-progresso");
  titulo.className = rodando ? "rodando" : "";
  titulo.textContent = rodando ? `Buscando: ${busca.rota}`
    : busca.estado === "concluida" ? `Busca concluída: ${busca.rota}` : `A busca parou com erro: ${busca.rota}`;
  document.getElementById("contador-busca").textContent = `[${busca.i}/${busca.n}]`;

  const linhas = busca.linhas.map((l) => (l.i !== null ? `[${l.i}/${l.n}] ${l.texto}` : l.texto));
  if (busca.erro) linhas.push(`Erro: ${busca.erro}`);
  const saida = document.getElementById("linhas-busca");
  saida.textContent = linhas.length ? linhas.join("\n") : "Começando a primeira busca…";
  saida.scrollTop = saida.scrollHeight;
  document.getElementById("quadro-progresso").hidden = false;
}

function fitaVoo(v, maisBarato) {
  const agencia = v.reserva_preco && v.reserva_preco < v.preco;
  const diasChegada = diasEntre(v.partida, v.chegada);
  const link = /^https:\/\//.test(v.link || "") ? v.link : null;
  return h("article", { class: "fita voo", "aria-label": `${dinheiro(v.menor_preco)}, ${textoDatasVoo(v)}` },
    h("div", { class: "fita-id" },
      h("div", { class: "preco" }, dinheiro(v.menor_preco)),
      h("div", { class: "fita-nome" }, agencia ? `total em ${v.reserva_onde}` : "total no Google Flights"),
      agencia ? h("div", { class: "fita-nome" }, `${dinheiro(v.preco)} no Google Flights`) : null,
      maisBarato ? h("span", { class: "estado" }, "Mais barato") : null,
    ),
    h("dl", { class: "fita-campos" },
      campo("Datas", textoDatasVoo(v)),
      campo("Saída", h("span", { class: "hora" }, v.partida.slice(11, 16))),
      campo("Chegada", h("span", { class: "hora" }, v.chegada.slice(11, 16)),
        diasChegada > 0 ? ` (+${plural(diasChegada, "dia", "dias")})` : ""),
      campo("Escalas", v.escalas === 0 ? "direto" : plural(v.escalas, "escala", "escalas")),
      campo("Duração da ida", textoDuracao(v.duracao_min)),
      campo("Companhias", v.companhias),
    ),
    h("div", { class: "fita-acoes" },
      link
        ? h("a", { class: "botao primario", href: link, target: "_blank", rel: "noopener noreferrer" }, "Abrir no Google Flights")
        : h("span", { class: "secundario" }, "Sem link")),
  );
}

function desenharResultados(busca) {
  const secao = document.getElementById("resultados");
  secao.hidden = busca.estado !== "concluida";
  if (secao.hidden) return;
  const voos = busca.resultados;
  const top = Math.max(1, Number(document.getElementById("form-busca").elements.top.value) || 10);
  const mostrar = todosResultados ? voos.length : Math.min(top, voos.length);
  const resumo = [`Preço total para ${textoPassageiros(busca.config)}; o melhor voo de cada combinação de datas`];
  if (mostrar < voos.length) resumo.push(`mostrando ${mostrar} de ${voos.length}`);
  document.getElementById("resumo-resultados").textContent = resumo.join(" · ");
  const lista = document.getElementById("lista-resultados");
  if (!voos.length) {
    lista.replaceChildren(h("p", { class: "vazio" },
      "Nenhum voo passou nos filtros. Afrouxe os filtros (preço, escalas, duração do voo) ou tente outras datas."));
    return;
  }
  const verTodas = () => {
    todosResultados = true;
    desenharResultados(busca);
  };
  const fitas = voos.slice(0, mostrar).map((v, k) => fitaVoo(v, k === 0));
  if (mostrar < voos.length) {
    fitas.push(h("button", { type: "button", class: "botao discreto mais", onclick: verTodas }, `Mostrar todas as ${voos.length} opções`));
  }
  lista.replaceChildren(...fitas);
}

function travarBusca(rodando) {
  const botao = document.getElementById("botao-buscar");
  botao.disabled = rodando;
  botao.textContent = rodando ? "Buscando…" : "Buscar voos";
}

function mostrarBusca(busca) {
  const nova = !buscaAtual || buscaAtual.id !== busca.id;
  buscaAtual = busca;
  travarBusca(busca.estado === "rodando");
  desenharProgresso(busca);
  desenharResultados(busca);
  const monitorar = document.getElementById("form-monitorar");
  const monitorada = document.getElementById("monitorada");
  if (nova) {
    monitorar.elements.nome.value = busca.config.nome;
    monitorar.elements.queda_percentual.value = 10;
    document.getElementById("erro-monitorar").hidden = true;
    monitorada.hidden = true;
  }
  monitorar.hidden = busca.estado !== "concluida" || !monitorada.hidden;
}

/** Consulta a busca a cada 1,5 s até ela terminar (continua mesmo em outra tela e avisa no fim). */
function acompanharBusca(id) {
  clearTimeout(acompanhamentoBusca);
  acompanhamentoBusca = setTimeout(async () => {
    acompanhamentoBusca = null;
    let busca;
    try {
      busca = await api("GET", `/api/busca/${id}`);
    } catch (erro) {
      avisar(erro.message, "erro");
      travarBusca(false);
      return;
    }
    mostrarBusca(busca);
    if (busca.estado === "rodando") acompanharBusca(id);
    else if (busca.estado === "concluida") avisar(`Busca concluída: ${plural(busca.resultados.length, "opção", "opções")} nos filtros.`);
    else avisar("A busca parou com erro; o motivo está na tela \"Buscar agora\".", "erro");
  }, 1500);
}

/** Ao abrir a tela: retoma a busca em andamento (ou mostra a última) e atualiza a contagem. */
async function carregarBusca() {
  if (!acompanhamentoBusca) {
    try {
      const busca = await api("GET", "/api/busca");
      if (busca) {
        if (!formBuscaMexido) preencherFormularioRota(document.getElementById("form-busca"), busca.config);
        mostrarBusca(busca);
        if (busca.estado === "rodando") acompanharBusca(busca.id);
      }
    } catch (erro) {
      avisar(`Não consegui ler a última busca: ${erro.message}`, "erro");
    }
  }
  atualizarPrevia();
}

function agendarPrevia() {
  formBuscaMexido = true;
  clearTimeout(previaTimer);
  previaTimer = setTimeout(atualizarPrevia, 400);
}

/** "N buscas no Google Flights" antes de buscar, pela mesma conta do servidor (POST /api/busca/previa). */
async function atualizarPrevia() {
  const alvo = document.getElementById("contagem");
  const pedido = ++previaPedida;
  let rota;
  try {
    rota = lerFormularioRota(document.getElementById("form-busca"));
  } catch {
    alvo.replaceChildren(h("span", { class: "secundario" },
      "Preencha origem, destino e as datas de ida para ver quantas buscas serão feitas."));
    return;
  }
  let previa;
  try {
    previa = await api("POST", "/api/busca/previa", { rota });
  } catch (erro) {
    if (pedido === previaPedida) alvo.replaceChildren(h("span", { class: "ruim" }, erro.message));
    return;
  }
  if (pedido !== previaPedida) return;
  if (!previa.n) {
    alvo.replaceChildren(h("span", { class: "ruim" }, "Nenhuma data de ida no futuro."));
    return;
  }
  alvo.replaceChildren(h("b", null, String(previa.n)),
    ` ${previa.n === 1 ? "busca" : "buscas"} no Google Flights, uma por combinação de datas`,
    previa.n > previa.limite ? h("span", { class: "atencao" }, ` · acima de ${previa.limite}, pede confirmação`) : "");
}

async function iniciarBusca(evento) {
  evento.preventDefault();
  const form = evento.currentTarget;
  const erroForm = document.getElementById("erro-busca");
  erroForm.hidden = true;
  let rota;
  try {
    rota = lerFormularioRota(form);
  } catch (erro) {
    mostrarErro(erroForm, erro.message);
    return;
  }
  const reservas = Math.max(0, Number(form.elements.reservas.value) || 0);
  travarBusca(true);
  try {
    const previa = await api("POST", "/api/busca/previa", { rota });
    if (!previa.n) throw new Error("Nenhuma data de ida no futuro para buscar.");
    let forcar = false;
    if (previa.n > previa.limite) {
      forcar = await confirmar("Muitas buscas de uma vez",
        `São ${previa.n} buscas. Acima de ${previa.limite}, o Google pode bloquear o acesso por um tempo, e a busca ` +
        "leva vários minutos. Reduza as datas ou busque mesmo assim.", `Fazer as ${previa.n} buscas`);
      if (!forcar) {
        travarBusca(false);
        return;
      }
    }
    const inicio = await api("POST", "/api/busca", { rota, reservas, forcar });
    todosResultados = false;
    mostrarBusca({ id: inicio.id, rota: inicio.rota.nome, config: inicio.rota, estado: "rodando", i: 0,
      n: inicio.n, linhas: [], resultados: [], erro: null });
    acompanharBusca(inicio.id);
  } catch (erro) {
    mostrarErro(erroForm, erro.message);
    travarBusca(false);
    if (erro.status === 409) carregarBusca(); // já há uma busca (de outra aba, por exemplo): acompanha aquela
  }
}

/** Diálogo "As 3 vagas estão em uso": devolve o nome da rota ativa escolhida, ou null se cancelou. */
function escolherSubstituta(ativas) {
  const dialogo = document.getElementById("dialogo-substituir");
  const botao = document.getElementById("botao-substituir");
  botao.disabled = true;
  const liberar = () => { botao.disabled = false; };
  document.getElementById("opcoes-substituir").replaceChildren(
    h("legend", { class: "sr" }, "Rota a substituir"),
    ...ativas.map((nome) => h("label", { class: "opcao" },
      h("input", { type: "radio", name: "substituir", value: nome, onchange: liberar }), h("span", null, nome))));
  return esperarResposta(dialogo, () => {
    const marcada = dialogo.querySelector('input[name="substituir"]:checked');
    return marcada ? marcada.value : null;
  });
}

async function monitorarBusca(evento) {
  evento.preventDefault();
  const form = evento.currentTarget;
  const erroForm = document.getElementById("erro-monitorar");
  erroForm.hidden = true;
  const nome = form.elements.nome.value.trim();
  const queda = Number(form.elements.queda_percentual.value);
  if (!nome) return mostrarErro(erroForm, "Dê um nome para a rota.");
  if (!(queda > 0 && queda < 100)) return mostrarErro(erroForm, "A queda para o alerta vai de 1 a 99%.");
  // Monitora a rota que foi buscada, não o formulário (que pode ter mudado depois da busca).
  const rota = { ...buscaAtual.config, nome, alerta: { queda_percentual: queda } };
  await comBotao(form.querySelector('[type="submit"]'), async () => {
    let substituir = null;
    try {
      try {
        await api("POST", "/api/rotas", { rota });
      } catch (erro) {
        if (!(erro.status === 409 && erro.dados && erro.dados.ativas)) throw erro;
        substituir = await escolherSubstituta(erro.dados.ativas);
        if (!substituir) return;
        await api("POST", "/api/rotas", { rota, substituir });
      }
    } catch (erro) {
      mostrarErro(erroForm, erro.message);
      return;
    }
    form.hidden = true;
    const monitorada = document.getElementById("monitorada");
    monitorada.replaceChildren(
      h("span", null, h("b", null, nome), " está sendo monitorada",
        substituir ? `, no lugar de "${substituir}"` : "", ". A próxima busca agendada já inclui esta rota. "),
      h("a", { href: "#rotas" }, "Ver buscas monitoradas"));
    monitorada.hidden = false;
    avisar(`Rota monitorada: ${nome}`);
  });
}

// --- histórico e gráficos ---------------------------------------------------------------------------------

let historicoRota = null; // rota escolhida no seletor (continua escolhida ao voltar para a tela)
let historico = null; // dados da rota escolhida: pontos, combinações, buscas, alertas, preco_max
let comboDestaque = null; // chave "ida|volta" da combinação em destaque no gráfico
let campoPreco = null; // "menor_nos_filtros" ou "menor_preco"; null = escolher pela rota
let larguraGrafico = 0;

const HORA = 3600000;

function chaveCombo(p) {
  return `${p.ida}|${p.volta || ""}`;
}

function textoCombo(c) {
  return c.volta ? `${diaCurto(c.ida)} → ${diaCurto(c.volta)}` : `${diaCurto(c.ida)} (só ida)`;
}

/** "−3,2%" / "+1,5%" / "0%". */
function porcento(valor, casas = 1) {
  const texto = Math.abs(valor).toFixed(casas).replace(".", ",").replace(/,0+$/, "");
  if (texto === "0") return "0%";
  return `${valor < 0 ? "−" : "+"}${texto}%`;
}

/** Combinações de datas (ordenadas pelo menor preço já visto) e buscas (uma por horário de execução).
 * `campo`: "menor_nos_filtros" ou "menor_preco" (todos os voos); vira `preco` em cada ponto. */
function organizarHistorico(pontosApi, campo) {
  const combos = new Map();
  const buscas = new Map();
  for (const p of pontosApi.map((ponto) => ({ ...ponto, preco: ponto[campo] }))) {
    const chave = chaveCombo(p);
    if (!combos.has(chave)) combos.set(chave, { chave, ida: p.ida, volta: p.volta, pontos: [] });
    combos.get(chave).pontos.push(p);
    if (!buscas.has(p.buscado_em)) buscas.set(p.buscado_em, { iso: p.buscado_em, t: new Date(p.buscado_em).getTime(), pontos: [] });
    buscas.get(p.buscado_em).pontos.push(p);
  }
  for (const c of combos.values()) {
    for (const p of c.pontos) {
      if (p.preco !== null && (!c.menor || p.preco < c.menor.preco)) c.menor = p;
    }
    c.ultimo = c.pontos[c.pontos.length - 1];
  }
  const preco = (c) => (c.menor ? c.menor.preco : Infinity);
  const listaCombos = [...combos.values()].sort((a, b) => preco(a) - preco(b) || a.chave.localeCompare(b.chave));
  // Uma execução grava tudo com o mesmo horário, mas o banco antigo tem um horário por combinação (segundos de
  // diferença): horários seguidos com até 2 min entre si contam como a mesma busca.
  const execucoes = [];
  for (const b of [...buscas.values()].sort((a, b) => a.t - b.t)) {
    const anterior = execucoes[execucoes.length - 1];
    if (anterior && b.t - anterior.tFim <= 2 * 60000) {
      anterior.pontos.push(...b.pontos);
      anterior.tFim = b.t;
    } else {
      execucoes.push({ ...b, tFim: b.t });
    }
  }
  for (const b of execucoes) {
    b.maisBarato = b.pontos.filter((p) => p.preco !== null)
      .reduce((a, p) => (!a || p.preco < a.preco ? p : a), null);
  }
  return { combos: listaCombos, buscas: execucoes };
}

async function carregarHistorico() {
  const seletor = document.getElementById("rota-historico");
  let lista;
  try {
    lista = await api("GET", "/api/historico");
  } catch (erro) {
    mostrarHistoricoVazio(`Não consegui ler o histórico: ${erro.message}`);
    return;
  }
  const comDados = new Set(lista.rotas);
  const removidas = lista.rotas.filter((nome) => !lista.monitoradas.includes(nome));
  if (!lista.monitoradas.length && !removidas.length) {
    seletor.replaceChildren();
    mostrarHistoricoVazio("Ainda não há buscas no histórico. Elas aparecem aqui depois da primeira execução da tarefa agendada.");
    return;
  }
  const opcao = (nome) => h("option", { value: nome }, comDados.has(nome) ? nome : `${nome} (sem buscas ainda)`);
  seletor.replaceChildren(...[
    lista.monitoradas.length && h("optgroup", { label: "Monitoradas" }, lista.monitoradas.map(opcao)),
    removidas.length && h("optgroup", { label: "Removidas (só no histórico)" }, removidas.map(opcao)),
  ].filter(Boolean));
  const todas = [...lista.monitoradas, ...removidas];
  if (!todas.includes(historicoRota)) {
    historicoRota = lista.monitoradas.find((nome) => comDados.has(nome)) || removidas[0] || todas[0];
    comboDestaque = null;
  }
  seletor.value = historicoRota;
  await mostrarRotaHistorico();
}

function mostrarHistoricoVazio(texto) {
  const vazio = document.getElementById("historico-vazio");
  vazio.textContent = texto;
  vazio.hidden = false;
  document.getElementById("historico-conteudo").hidden = true;
}

async function mostrarRotaHistorico() {
  const nome = historicoRota;
  const consulta = encodeURIComponent(nome);
  let dados, alertas, relatorio;
  try {
    [dados, alertas, relatorio] = await Promise.all([
      api("GET", `/api/historico?rota=${consulta}`),
      api("GET", `/api/alertas?rota=${consulta}`),
      api("GET", "/api/relatorio"),
    ]);
  } catch (erro) {
    mostrarHistoricoVazio(`Não consegui ler o histórico: ${erro.message}`);
    return;
  }
  if (nome !== historicoRota) return; // a pessoa trocou de rota enquanto carregava
  if (!dados.pontos.length) {
    mostrarHistoricoVazio("Esta rota ainda não foi buscada. A tarefa agendada busca as rotas monitoradas 12 vezes por dia.");
    return;
  }
  const temFiltrados = dados.pontos.some((p) => p.menor_nos_filtros !== null);
  historico = {
    pontosApi: dados.pontos, alertas, precoMax: dados.preco_max, temFiltrados,
    menorGeral: Math.min(...dados.pontos.map((p) => p.menor_preco)),
    horarios: relatorio.rotas.find((r) => r.rota === nome),
  };
  // Sem nenhum voo nos filtros, o gráfico "só nos filtros" ficaria vazio: começa em "todos os voos".
  if (!campoPreco || !temFiltrados) campoPreco = temFiltrados ? "menor_nos_filtros" : "menor_preco";

  document.getElementById("historico-vazio").hidden = true;
  document.getElementById("historico-conteudo").hidden = false;
  desenharAlertas(alertas);
  desenharHorarios(historico.horarios);
  aplicarCampoPreco();
}

/** Monta as combinações com o campo de preço escolhido e desenha o gráfico e a tabela. */
function aplicarCampoPreco() {
  Object.assign(historico, organizarHistorico(historico.pontosApi, campoPreco));
  const { buscas, combos, temFiltrados, precoMax, menorGeral } = historico;
  if (!combos.some((c) => c.chave === comboDestaque)) comboDestaque = combos[0].chave;
  const nosFiltros = campoPreco === "menor_nos_filtros";

  for (const botao of document.querySelectorAll(".alternar button")) {
    botao.setAttribute("aria-pressed", String(botao.dataset.campo === campoPreco));
    botao.disabled = botao.dataset.campo === "menor_nos_filtros" && !temFiltrados;
  }
  const aviso = document.getElementById("aviso-filtros");
  aviso.hidden = temFiltrados;
  aviso.textContent = precoMax && menorGeral > precoMax
    ? `Nenhum voo desta rota passou nos filtros até agora: o mais barato encontrado foi ${dinheiro(menorGeral)}, ` +
      `acima do preço máximo de ${dinheiro(precoMax)}. O gráfico mostra o menor preço de todos os voos.`
    : "Nenhum voo desta rota passou nos filtros até agora. O gráfico mostra o menor preço de todos os voos.";
  document.getElementById("titulo-grafico").textContent =
    nosFiltros ? "Menor preço nos filtros, a cada busca" : "Menor preço de todos os voos, a cada busca";
  document.getElementById("coluna-menor").textContent = nosFiltros ? "Menor nos filtros" : "Menor (todos os voos)";
  document.getElementById("resumo-historico").textContent =
    `${plural(buscas.length, "busca", "buscas")} de ${data(buscas[0].iso)} a ${data(buscas[buscas.length - 1].iso)} · ` +
    plural(combos.length, "combinação de datas", "combinações de datas");
  larguraGrafico = 0;
  desenharGraficoPrecos();
  desenharTabelaCombinacoes();
}

/** Os gráficos são desenhados na largura real; ao mudar a largura da janela, desenha de novo. */
function observarLarguraHistorico() {
  const conteudo = document.getElementById("historico-conteudo");
  let largura = 0;
  new ResizeObserver(() => {
    if (!historico || !conteudo.clientWidth || conteudo.clientWidth === largura) return;
    largura = conteudo.clientWidth;
    desenharGraficoPrecos();
    desenharHorarios(historico.horarios);
  }).observe(conteudo);
}

function destacarCombo(chave) {
  comboDestaque = chave;
  larguraGrafico = 0;
  desenharGraficoPrecos();
  desenharTabelaCombinacoes();
}

/** Escala com valores redondos: {inicio, fim, marcas}. */
function escalaBonita(minimo, maximo, quantas) {
  if (minimo === maximo) {
    minimo -= Math.max(1, Math.abs(minimo) * 0.05);
    maximo += Math.max(1, Math.abs(maximo) * 0.05);
  }
  const bruto = (maximo - minimo) / quantas;
  const ordem = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((f) => f * ordem).find((p) => p >= bruto);
  const inicio = Math.floor(minimo / passo) * passo;
  const fim = Math.ceil(maximo / passo) * passo;
  const marcas = [];
  for (let v = inicio; v <= fim + passo / 2; v += passo) marcas.push(Math.round(v * 1000) / 1000);
  return { inicio, fim, marcas };
}

/** Marcas do eixo de tempo em horas ou dias redondos, no máximo `maximo` delas. */
function marcasTempo(t0, t1, maximo) {
  const passos = [1, 2, 3, 6, 12, 24, 48, 96, 168];
  const horas = passos.find((p) => (t1 - t0) / (p * HORA) <= maximo) || passos[passos.length - 1];
  const d = new Date(t0);
  d.setMinutes(0, 0, 0);
  if (horas >= 24) d.setHours(0);
  while (d.getTime() < t0 || (horas < 24 && d.getHours() % horas)) d.setHours(d.getHours() + 1);
  const marcas = [];
  let diaAnterior = null;
  for (; d.getTime() <= t1; d.setHours(d.getHours() + horas)) {
    const dia = `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
    const hora = `${String(d.getHours()).padStart(2, "0")}h`;
    const texto = horas >= 24 ? dia : dia !== diaAnterior ? `${dia} ${hora}` : hora;
    marcas.push({ t: d.getTime(), texto });
    diaAnterior = dia;
  }
  return marcas;
}

/** A dica flutuante de um gráfico (uma por gráfico). `itens`: [{chave, valor, texto}]. */
function mostrarDica(alvo, x, y, quando, itens) {
  let dica = alvo.querySelector(".dica-grafico");
  if (!dica) {
    dica = h("div", { class: "dica-grafico", role: "status" });
    alvo.append(dica);
  }
  dica.replaceChildren(
    h("div", { class: "quando" }, quando),
    ...itens.map((item) => h("div", { class: "item" },
      item.chave && h("span", { class: `chave ${item.chave}`, "aria-hidden": "true" }),
      item.valor && h("span", { class: "valor" }, item.valor),
      h("span", null, item.texto))),
  );
  dica.hidden = false;
  const largura = dica.offsetWidth;
  const esquerda = x + 14 + largura > alvo.clientWidth ? x - 14 - largura : x + 14;
  dica.style.transform = `translate(${Math.max(0, esquerda)}px, ${y}px)`;
}

function esconderDica(alvo) {
  const dica = alvo.querySelector(".dica-grafico");
  if (dica) dica.hidden = true;
}

/** Gráfico de linha: o menor preço nos filtros de cada combinação de datas ao longo das buscas. A combinação em
 * destaque fica em azul e as outras em cinza; linha do preço máximo da rota e losangos nos alertas enviados. */
function desenharGraficoPrecos() {
  const alvo = document.getElementById("grafico-precos");
  const largura = alvo.clientWidth;
  if (!historico || !largura || largura === larguraGrafico) return;
  larguraGrafico = largura;
  const { combos, buscas, alertas, precoMax } = historico;
  const destaque = combos.find((c) => c.chave === comboDestaque);
  const estreito = largura < 520;
  const altura = estreito ? 240 : 300;
  const m = { cima: 16, dir: estreito ? 56 : 72, baixo: 28, esq: estreito ? 60 : 68 };
  const larguraUtil = largura - m.esq - m.dir;
  const alturaUtil = altura - m.cima - m.baixo;

  const precos = buscas.flatMap((b) => b.pontos.map((p) => p.preco)).filter((v) => v !== null);
  const legenda = [];
  if (!precos.length) {
    document.getElementById("legenda-grafico").replaceChildren();
    alvo.replaceChildren(h("p", { class: "vazio" }, "Nenhum voo passou nos filtros desta rota até agora. A tabela abaixo mostra as buscas feitas."));
    return;
  }
  const precosAlerta = alertas.map((a) => a.preco);
  let minimo = Math.min(...precos, ...precosAlerta);
  let maximo = Math.max(...precos, ...precosAlerta);
  // O preço máximo entra no gráfico só se estiver perto dos preços; senão achataria as linhas.
  const limiteVisivel = precoMax && precoMax <= maximo * 1.3 && precoMax >= minimo * 0.7;
  if (limiteVisivel) {
    minimo = Math.min(minimo, precoMax);
    maximo = Math.max(maximo, precoMax);
  }
  const escalaY = escalaBonita(minimo, maximo, estreito ? 4 : 5);
  const y = (v) => m.cima + alturaUtil * (1 - (v - escalaY.inicio) / (escalaY.fim - escalaY.inicio));

  let t0 = Math.min(buscas[0].t, ...alertas.map((a) => new Date(a.enviado_em).getTime()));
  let t1 = Math.max(buscas[buscas.length - 1].t, ...alertas.map((a) => new Date(a.enviado_em).getTime()));
  if (t1 - t0 < HORA) {
    t0 -= HORA;
    t1 += HORA;
  }
  const x = (t) => m.esq + larguraUtil * ((t - t0) / (t1 - t0));

  const grade = escalaY.marcas.map((v) => s("g", null,
    s("line", { class: "grade", x1: m.esq, x2: largura - m.dir, y1: y(v), y2: y(v) }),
    s("text", { class: "eixo-texto", x: m.esq - 8, y: y(v) + 4, "text-anchor": "end" }, dinheiro(v))));
  const marcasX = marcasTempo(t0, t1, Math.max(2, Math.floor(larguraUtil / 84)));
  const eixoX = marcasX.map((mx) => s("text", { class: "eixo-texto", x: x(mx.t), y: altura - 8, "text-anchor": "middle" }, mx.texto));

  const caminho = (c) => {
    let d = "";
    let aberto = false;
    for (const p of c.pontos) {
      if (p.preco === null) {
        aberto = false; // buscada, mas sem voo nos filtros: a linha quebra
        continue;
      }
      d += `${aberto ? "L" : "M"}${x(new Date(p.buscado_em).getTime()).toFixed(1)},${y(p.preco).toFixed(1)}`;
      aberto = true;
    }
    return d;
  };
  const outras = combos.filter((c) => c !== destaque).map((c) => s("path", { class: "linha", d: caminho(c) }));
  const pontosDestaque = destaque.pontos.filter((p) => p.preco !== null);
  const ultimo = pontosDestaque[pontosDestaque.length - 1];
  const losango = (cx, cy) => `M${cx},${cy - 6}L${cx + 6},${cy}L${cx},${cy + 6}L${cx - 6},${cy}Z`;

  const mira = s("line", { class: "mira", y1: m.cima, y2: altura - m.baixo, visibility: "hidden" });
  const alvoEventos = s("rect", { x: m.esq, y: 0, width: larguraUtil, height: altura - m.baixo, fill: "transparent" });
  const svg = s("svg", {
    viewBox: `0 0 ${largura} ${altura}`, height: altura, tabindex: 0, role: "img",
    "aria-label": `Gráfico do menor preço nos filtros a cada busca. Em destaque: ${textoCombo(destaque)}. ` +
      "Os valores também estão na tabela abaixo.",
  },
    grade,
    limiteVisivel && s("line", { class: "limite", x1: m.esq, x2: largura - m.dir, y1: y(precoMax), y2: y(precoMax) }),
    limiteVisivel && s("text", { class: "eixo-texto", x: m.esq + 4, y: y(precoMax) - 6 }, `preço máximo ${dinheiro(precoMax)}`),
    eixoX,
    outras,
    s("path", { class: "linha destaque", d: caminho(destaque) }),
    pontosDestaque.length <= 60 && pontosDestaque.map((p) => s("circle", {
      class: "ponto", cx: x(new Date(p.buscado_em).getTime()), cy: y(p.preco), r: 4,
    })),
    alertas.map((a) => s("path", { class: "alerta", d: losango(x(new Date(a.enviado_em).getTime()), y(a.preco)) })),
    ultimo && s("text", { class: "rotulo", x: x(new Date(ultimo.buscado_em).getTime()) + 9, y: y(ultimo.preco) + 4 },
      dinheiro(ultimo.preco)),
    mira,
    alvoEventos,
  );
  alvo.replaceChildren(svg);

  // Mira: encaixa na busca mais próxima do ponteiro (ou das setas do teclado) e mostra a dica.
  let atual = null;
  const mostrar = (i) => {
    atual = Math.max(0, Math.min(buscas.length - 1, i));
    const b = buscas[atual];
    const bx = x(b.t);
    mira.setAttribute("x1", bx);
    mira.setAttribute("x2", bx);
    mira.setAttribute("visibility", "visible");
    const doDestaque = b.pontos.find((p) => chaveCombo(p) === comboDestaque);
    const itens = [];
    if (doDestaque) {
      itens.push(doDestaque.preco !== null
        ? { chave: "destaque", valor: dinheiro(doDestaque.preco), texto: textoCombo(destaque) }
        : { chave: "destaque", texto: `${textoCombo(destaque)}: nenhum voo nos filtros` });
    }
    if (b.maisBarato && !(doDestaque && doDestaque.preco !== null && doDestaque.preco <= b.maisBarato.preco)) {
      itens.push({ chave: "apagada", valor: dinheiro(b.maisBarato.preco), texto: `mais barato: ${textoCombo(b.maisBarato)}` });
    }
    // O alerta é gravado no fim da execução (no banco antigo, segundos depois do último horário da busca).
    const daBusca = (a) => new Date(a.enviado_em).getTime() >= b.t && new Date(a.enviado_em).getTime() <= b.tFim + 2 * 60000;
    for (const a of alertas.filter(daBusca)) {
      itens.push({ chave: "alerta", valor: dinheiro(a.preco), texto: `alerta enviado (${textoCombo(a)})` });
    }
    if (!b.maisBarato) itens.push({ texto: "nenhum voo nos filtros nesta busca" });
    itens.push({ texto: plural(b.pontos.length, "combinação buscada", "combinações buscadas") });
    mostrarDica(alvo, bx, m.cima, dataHora(b.iso), itens);
  };
  const maisProxima = (evento) => {
    const caixa = svg.getBoundingClientRect();
    const px = ((evento.clientX - caixa.left) / caixa.width) * largura;
    let melhor = 0;
    buscas.forEach((b, i) => {
      if (Math.abs(x(b.t) - px) < Math.abs(x(buscas[melhor].t) - px)) melhor = i;
    });
    return melhor;
  };
  const esconder = () => {
    mira.setAttribute("visibility", "hidden");
    esconderDica(alvo);
  };
  alvoEventos.addEventListener("pointermove", (e) => mostrar(maisProxima(e)));
  alvoEventos.addEventListener("pointerleave", () => {
    if (document.activeElement !== svg) esconder();
  });
  // Clique: destaca a combinação mais barata daquela busca.
  alvoEventos.addEventListener("click", (e) => {
    const b = buscas[maisProxima(e)];
    if (b.maisBarato && chaveCombo(b.maisBarato) !== comboDestaque) destacarCombo(chaveCombo(b.maisBarato));
  });
  svg.addEventListener("focus", () => mostrar(atual ?? buscas.length - 1));
  svg.addEventListener("blur", esconder);
  svg.addEventListener("keydown", (e) => {
    const passo = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
    if (passo) mostrar((atual ?? buscas.length - 1) + passo);
    else if (e.key === "Home") mostrar(0);
    else if (e.key === "End") mostrar(buscas.length - 1);
    else if (e.key === "Enter" && atual !== null && buscas[atual].maisBarato) {
      destacarCombo(chaveCombo(buscas[atual].maisBarato));
      return;
    } else return;
    e.preventDefault();
  });

  legenda.push(h("li", null, h("span", { class: "chave", "aria-hidden": "true" }), `${textoCombo(destaque)} (em destaque)`));
  if (combos.length > 1) {
    legenda.push(h("li", null, h("span", { class: "chave apagada", "aria-hidden": "true" }),
      `outras ${plural(combos.length - 1, "combinação", "combinações")}`));
  }
  if (limiteVisivel) legenda.push(h("li", null, h("span", { class: "chave limite", "aria-hidden": "true" }), "preço máximo da rota"));
  else if (precoMax) {
    legenda.push(h("li", null, `preço máximo ${dinheiro(precoMax)}, ${precoMax > maximo ? "acima" : "abaixo"} da área do gráfico`));
  }
  if (alertas.length) legenda.push(h("li", null, h("span", { class: "chave alerta", "aria-hidden": "true" }), "alerta enviado"));
  document.getElementById("legenda-grafico").replaceChildren(...legenda);
}

function desenharTabelaCombinacoes() {
  const preco = (p) => (p.preco !== null ? dinheiro(p.preco) : h("span", { class: "secundario" }, "nenhum"));
  const linhas = historico.combos.map((c) => h("tr", {
    tabindex: 0,
    "aria-current": c.chave === comboDestaque ? "true" : null,
    title: "Destacar no gráfico",
    onclick: () => destacarCombo(c.chave),
    onkeydown: (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        destacarCombo(c.chave);
      }
    },
  },
    h("td", null, diaCurto(c.ida)),
    h("td", null, c.volta ? diaCurto(c.volta) : "só ida"),
    h("td", { class: "num coluna-dias" }, c.volta ? diasEntre(c.ida, c.volta) : "—"),
    h("td", { class: "num" }, c.menor ? h("b", null, dinheiro(c.menor.preco)) : h("span", { class: "secundario" }, "nenhum")),
    h("td", null, c.menor ? dataHora(c.menor.buscado_em) : ""),
    h("td", { class: "num" }, preco(c.ultimo)),
    h("td", { class: "num" }, c.pontos.length),
  ));
  document.querySelector("#tabela-combinacoes tbody").replaceChildren(...linhas);
}

function desenharAlertas(alertas) {
  const lista = document.getElementById("lista-alertas");
  if (!alertas.length) {
    lista.replaceChildren(h("li", { class: "secundario" }, "Nenhum alerta enviado para esta rota."));
    return;
  }
  lista.replaceChildren(...alertas.map((a) => h("li", null,
    h("span", { class: "preco-alerta" }, dinheiro(a.preco)),
    h("span", null, textoCombo(a)),
    h("span", { class: "secundario" }, `${dataHora(a.enviado_em)} · ${a.companhias}`),
  )));
}

/** Barra com a ponta de dados arredondada (4 px) e o lado do zero reto. */
function caminhoBarra(x0, largura, yZero, yValor) {
  const r = Math.min(4, Math.abs(yValor - yZero), largura / 2);
  const x1 = x0 + largura;
  if (yValor < yZero) {
    return `M${x0},${yZero}V${yValor + r}Q${x0},${yValor} ${x0 + r},${yValor}H${x1 - r}Q${x1},${yValor} ${x1},${yValor + r}V${yZero}Z`;
  }
  return `M${x0},${yZero}V${yValor - r}Q${x0},${yValor} ${x0 + r},${yValor}H${x1 - r}Q${x1},${yValor} ${x1},${yValor - r}V${yZero}Z`;
}

/** Colunas divergentes do desvio do preço em relação à média: para cima (laranja) = mais caro, para baixo
 * (azul) = mais barato. Rótulo só na coluna mais barata; o resto fica na dica e no eixo. */
function graficoDesvios(alvo, itens, rotulo, detalhe) {
  const largura = alvo.clientWidth || 480;
  const altura = 170;
  const m = { cima: 18, dir: 8, baixo: 24, esq: 44 };
  const larguraUtil = largura - m.esq - m.dir;
  const alturaUtil = altura - m.cima - m.baixo;
  const extremo = Math.max(1, ...itens.map((i) => Math.abs(i.desvio)));
  const escala = escalaBonita(-extremo, extremo, 4);
  const y = (v) => m.cima + alturaUtil * (1 - (v - escala.inicio) / (escala.fim - escala.inicio));
  const faixa = larguraUtil / itens.length;
  const larguraBarra = Math.min(24, faixa * 0.6);
  const maisBarato = itens.reduce((a, i) => (i.desvio < a.desvio ? i : a));

  const colunas = itens.map((item, i) => {
    const cx = m.esq + faixa * (i + 0.5);
    const alvoBarra = s("rect", {
      class: "barra-alvo", x: m.esq + faixa * i, y: m.cima, width: faixa, height: alturaUtil, tabindex: 0,
      "aria-label": `${rotulo(item)}: ${porcento(item.desvio)} em relação à média, ${plural(item.buscas, "busca", "buscas")}`,
    });
    const mostrar = () => mostrarDica(alvo, cx, m.cima, rotulo(item), [
      { valor: porcento(item.desvio), texto: item.desvio < 0 ? "abaixo da média" : "acima da média" },
      { texto: detalhe(item) },
    ]);
    alvoBarra.addEventListener("pointerenter", mostrar);
    alvoBarra.addEventListener("focus", mostrar);
    alvoBarra.addEventListener("pointerleave", () => esconderDica(alvo));
    alvoBarra.addEventListener("blur", () => esconderDica(alvo));
    return s("g", null,
      alvoBarra,
      Math.abs(y(item.desvio) - y(0)) >= 0.5 && s("path", {
        class: `barra${item.desvio > 0 ? " mais-caro" : ""}`, d: caminhoBarra(cx - larguraBarra / 2, larguraBarra, y(0), y(item.desvio)),
        "pointer-events": "none",
      }),
      s("text", { class: "eixo-texto", x: cx, y: altura - 6, "text-anchor": "middle" }, rotulo(item)),
      item === maisBarato && item.desvio < 0 && s("text", {
        class: "rotulo", x: cx, y: Math.min(y(item.desvio) + 14, m.cima + alturaUtil + 2), "text-anchor": "middle",
      }, porcento(item.desvio)),
    );
  });
  alvo.replaceChildren(s("svg", { viewBox: `0 0 ${largura} ${altura}`, height: altura },
    escala.marcas.map((v) => s("g", null,
      s("line", { class: v === 0 ? "zero" : "grade", x1: m.esq, x2: largura - m.dir, y1: y(v), y2: y(v) }),
      s("text", { class: "eixo-texto", x: m.esq - 6, y: y(v) + 4, "text-anchor": "end" }, porcento(v)))),
    colunas,
  ));
}

function desenharHorarios(dados) {
  const alvo = document.getElementById("relatorio-horarios");
  if (!dados || !dados.por_hora.length) {
    alvo.replaceChildren(h("p", { class: "aviso" },
      "Poucos dados ainda: cada combinação de datas precisa de pelo menos 2 buscas para comparar os horários."));
    return;
  }
  const melhorHora = dados.por_hora.reduce((a, i) => (i.desvio < a.desvio ? i : a));
  const menosBuscas = Math.min(...dados.por_hora.map((i) => i.buscas));
  const horaTexto = (i) => `${String(i.hora).padStart(2, "0")}h`;
  const graficoHora = h("div", { class: "grafico" });
  const graficoDia = h("div", { class: "grafico" });
  alvo.replaceChildren(h("div", { class: "horarios" },
    h("p", { class: "explica" }, "Quanto o menor preço de cada busca ficou acima ou abaixo da média da sua combinação de datas, ",
      `pela hora e pelo dia da semana em que a busca rodou (${plural(dados.buscas, "busca", "buscas")}).`),
    menosBuscas < 10 && h("p", { class: "aviso" }, "Ainda são poucos dados (algumas horas têm menos de 10 buscas): ",
      "diferenças pequenas podem ser acaso."),
    melhorHora.desvio < 0 && h("p", { class: "resumo-horario" }, "Mais barato, em média: buscas das ",
      h("b", null, horaTexto(melhorHora)), ` (${porcento(melhorHora.desvio)} em relação à média).`),
    h("ul", { class: "legenda-grafico" },
      h("li", null, h("span", { class: "chave mais-barato", "aria-hidden": "true" }), "abaixo da média"),
      h("li", null, h("span", { class: "chave mais-caro", "aria-hidden": "true" }), "acima da média")),
    h("h3", null, "Por hora do dia"), graficoHora,
    h("h3", null, "Por dia da semana",
      dados.por_dia.length < 7 && h("span", { class: "secundario" }, ` (só ${plural(dados.por_dia.length, "dia", "dias")} com buscas até agora)`)),
    graficoDia,
  ));
  graficoDesvios(graficoHora, dados.por_hora, horaTexto,
    (i) => `${plural(i.buscas, "busca", "buscas")} · ${plural(i.minimos, "mínimo histórico", "mínimos históricos")}`);
  graficoDesvios(graficoDia, dados.por_dia, (i) => i.nome, (i) => plural(i.buscas, "busca", "buscas"));
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

function linhaEndereco(endereco) {
  const campo = h("input", { class: "endereco", readonly: true, value: endereco.url, spellcheck: "false",
    "aria-label": `Endereço ${endereco.ip}`, onfocus: (evento) => evento.target.select() });
  return h("div", { class: "linha-endereco" },
    h("span", { class: "hora" }, endereco.ip),
    campo,
    h("button", { type: "button", class: "botao", onclick: () => copiarEndereco(campo) }, "Copiar"));
}

/** Copia o endereço. A API de área de transferência só existe em página segura (https ou localhost): no celular,
 * por http://IP, cai no select + copy; se nem isso, a pessoa copia à mão (o texto já fica selecionado). */
async function copiarEndereco(campo) {
  try {
    await navigator.clipboard.writeText(campo.value);
  } catch {
    campo.select();
    if (!document.execCommand("copy")) {
      avisar("Não consegui copiar sozinho: o endereço está selecionado, copie à mão.", "erro");
      return;
    }
  }
  avisar("Endereço copiado.");
}

function quadroAcesso(acesso) {
  if (!acesso.rede) {
    return [
      h("p", null, h("span", { class: "atencao" }, "Desligado."), " A interface só responde neste PC."),
      h("p", { class: "explica" }, "Para abrir no celular, desligue a interface (botão abaixo) e dê dois cliques em ",
        "\"Flight Scanner (celular).cmd\". Esta tela vai mostrar o endereço para digitar no celular."),
    ];
  }
  if (!acesso.enderecos.length) {
    return [h("p", { class: "ruim" }, "Não achei o endereço deste PC na rede. Ele está conectado ao Wi-Fi?")];
  }
  const [principal, ...outros] = acesso.enderecos;
  return [
    h("p", null, h("span", { class: "ok" }, "Ligado."),
      " No celular, conectado ao mesmo Wi-Fi, abra o endereço abaixo. Só na primeira vez: depois o celular lembra."),
    linhaEndereco(principal),
    outros.length
      ? h("details", null, h("summary", null, `Outros endereços deste PC (${outros.length})`),
        h("p", { class: "dica" }, "Se o primeiro não abrir, tente um destes: com VPN ou máquina virtual, o PC tem mais de uma rede."),
        ...outros.map(linhaEndereco))
      : null,
    h("p", { class: "explica" }, "Quem tiver este endereço controla a interface: não o publique nem o mande para outras pessoas. ",
      "A conexão não é criptografada (HTTP), então use só no Wi-Fi de casa. ",
      "Para trocar o token e desconectar os celulares, apague a linha INTERFACE_TOKEN do arquivo .env e abra o atalho de novo. ",
      "Se o celular não abrir a página, o suspeito é o Firewall do Windows (libere o Python só em redes privadas): veja o README."),
  ];
}

async function carregarAcesso() {
  const corpo = document.querySelector("#quadro-acesso .corpo");
  try {
    corpo.replaceChildren(...quadroAcesso(await api("GET", "/api/acesso")));
  } catch (erro) {
    corpo.replaceChildren(h("p", { class: "ruim" }, `Não consegui ler o acesso: ${erro.message}`));
  }
}

async function carregarStatus() {
  pararAcompanhamento();
  carregarAcesso();
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
      // Sem resposta, o acompanhamento para: os botões voltam (se ainda estiver rodando, o servidor responde 409).
      avisar(`${erro.message} Use "Atualizar" para ver o estado da execução.`, "erro");
      for (const id of ["rodar-agora", "rodar-teste"]) document.getElementById(id).disabled = false;
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

async function desligarInterface(evento) {
  const botao = evento.currentTarget; // vira null depois do await
  const ok = await confirmar("Desligar a interface",
    "Encerra o servidor desta página. Uma busca avulsa ou um \"Rodar agora\" em andamento pode ser interrompido; " +
    "as buscas agendadas continuam normalmente.", "Desligar", { perigo: true });
  if (!ok) return;
  await comBotao(botao, async () => {
    try {
      await api("POST", "/api/desligar", { confirmar: true });
    } catch (erro) {
      avisar(erro.message, "erro");
      return;
    }
    pararAcompanhamento();
    document.body.replaceChildren(h("main", null,
      h("h1", null, "Interface desligada"),
      h("p", { class: "explica" }, "Pode fechar esta aba. Para abrir de novo, dê dois cliques em \"Flight Scanner.cmd\".")));
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

for (const lugar of document.querySelectorAll("[data-campos-rota]")) {
  lugar.replaceWith(document.getElementById("campos-rota").content.cloneNode(true));
}
document.getElementById("form-busca").addEventListener("submit", iniciarBusca);
document.getElementById("form-busca").addEventListener("input", agendarPrevia);
document.getElementById("form-monitorar").addEventListener("submit", monitorarBusca);
document.getElementById("form-rota").addEventListener("submit", salvarEdicao);
document.getElementById("form-rota").addEventListener("input", atualizarAvisoPassageiros);
document.querySelector("#dialogo-editar [data-fechar]").addEventListener("click", () => document.getElementById("dialogo-editar").close());
document.getElementById("atualizar-status").addEventListener("click", carregarStatus);
document.getElementById("rodar-agora").addEventListener("click", () => executar(false));
document.getElementById("rodar-teste").addEventListener("click", () => executar(true));
document.getElementById("testar-notificacao").addEventListener("click", testarNotificacao);
document.getElementById("desligar-interface").addEventListener("click", desligarInterface);
document.getElementById("rota-historico").addEventListener("change", (evento) => {
  historicoRota = evento.target.value;
  comboDestaque = null;
  campoPreco = null;
  mostrarRotaHistorico();
});
for (const botao of document.querySelectorAll(".alternar button")) {
  botao.addEventListener("click", () => {
    campoPreco = botao.dataset.campo;
    aplicarCampoPreco();
  });
}
observarLarguraHistorico();
window.addEventListener("hashchange", mostrarTela);

mostrarTela();
if (location.hash.slice(1) !== "status") {
  api("GET", "/api/status").then((s) => desenharProxima(s.tarefas)).catch(() => {});
}
