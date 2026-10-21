"use strict";

// Interface do Jarvis. Recebe eventos do cérebro (SSE) por `jarvis.aplicar(evento)`.
// `?demo=1` mostra dados de exemplo sem servidor; `&quadro=1` monta direto o quadro final (para capturas).

(() => {
  const $ = (id) => document.getElementById(id);
  const parametros = new URLSearchParams(location.search);
  const DEMO = parametros.has("demo");

  const ROTULO_ESTADO = {
    ocioso: "Pronto",
    ouvindo: "Ouvindo",
    pensando: "Pensando",
    falando: "Falando",
    desconectado: "Jarvis desconectado. Tentando de novo…",
  };
  const ROTULO_SESSAO = {
    working: "trabalhando",
    done: "concluiu",
    waiting: "aguarda o senhor",
    permission: "pede permissão",
    blocked: "travou",
    idle: "parado",
  };
  const PRECISA_DO_SENHOR = new Set(["waiting", "permission", "blocked"]);
  const NOME_PENDENCIA = { enviar: "Confirmar envio", regra: "Nova regra", lancar: "Abrir agente", permissao: "Permissão" };
  const MAX_MENSAGENS = 12;

  let respostaAtual = null;
  let ultimasSessoes = null;

  // ---------- texto ----------

  function escapar(texto) {
    return texto.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function inline(texto) {
    return escapar(texto)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  // As linhas 🔊/🔇 são para a voz; na tela só aparecem se a resposta não tiver outro texto.
  function paraTela(texto) {
    const linhas = texto.split("\n");
    const escritas = linhas.filter((l) => !/^\s*(🔊|🔇)/.test(l));
    const sobra = escritas.join("\n").trim();
    if (sobra) return sobra;
    return linhas.filter((l) => /^\s*🔊/.test(l)).map((l) => l.replace(/^\s*🔊\s*/, "")).join(" ");
  }

  function markdownSimples(texto) {
    const blocos = [];
    let lista = null;
    for (const linha of paraTela(texto).split("\n")) {
      const item = linha.match(/^\s*[-•*]\s+(.*)$/);
      if (item) {
        lista = lista || [];
        lista.push(`<li>${inline(item[1])}</li>`);
        continue;
      }
      if (lista) { blocos.push(`<ul>${lista.join("")}</ul>`); lista = null; }
      if (linha.trim()) blocos.push(`<p>${inline(linha.replace(/^#+\s*/, ""))}</p>`);
    }
    if (lista) blocos.push(`<ul>${lista.join("")}</ul>`);
    return blocos.join("");
  }

  // ---------- conversa ----------

  function adicionarMensagem(papel, texto) {
    const artigo = document.createElement("article");
    artigo.className = `msg ${papel}`;
    artigo.dataset.texto = texto;
    artigo.innerHTML = papel === "jarvis" ? markdownSimples(texto) : `<p>${inline(texto)}</p>`;
    $("conversa").append(artigo);
    while ($("conversa").children.length > MAX_MENSAGENS) $("conversa").firstElementChild.remove();
    return artigo;
  }

  function delta(texto) {
    if (!respostaAtual) {
      respostaAtual = adicionarMensagem("jarvis", "");
      respostaAtual.classList.add("escrevendo");
    }
    respostaAtual.dataset.texto += texto;
    respostaAtual.innerHTML = markdownSimples(respostaAtual.dataset.texto);
  }

  function respostaFim(texto) {
    if (!respostaAtual) respostaAtual = adicionarMensagem("jarvis", "");
    respostaAtual.dataset.texto = texto ?? respostaAtual.dataset.texto;
    respostaAtual.innerHTML = markdownSimples(respostaAtual.dataset.texto);
    respostaAtual.classList.remove("escrevendo");
    if (!respostaAtual.textContent.trim()) respostaAtual.remove();
    respostaAtual = null;
  }

  // ---------- sessões em órbita ----------

  function tempoDesde(ms) {
    if (!ms) return "";
    const minutos = Math.max(0, Math.round((Date.now() - ms) / 60000));
    if (minutos < 1) return "agora";
    if (minutos < 60) return `há ${minutos} min`;
    const horas = Math.round(minutos / 60);
    return horas < 48 ? `há ${horas} h` : `há ${Math.round(horas / 24)} dias`;
  }

  function desenharSessoes(itens) {
    ultimasSessoes = itens;
    const ordenadas = [...itens].sort((a, b) =>
      (PRECISA_DO_SENHOR.has(b.estado) - PRECISA_DO_SENHOR.has(a.estado)) || a.projeto.localeCompare(b.projeto));
    const rx = Math.min(470, innerWidth * 0.3);
    const ry = Math.min(185, innerHeight * 0.18);
    const lista = $("sessoes");
    lista.replaceChildren();
    const linhas = [`<ellipse cx="50%" cy="50%" rx="${rx}" ry="${ry}"/>`];

    // Distribui em leque a partir do topo, deixando livre a faixa de baixo (onde fica o estado do núcleo);
    // os primeiros da lista (quem precisa do senhor) ficam nas posições mais altas.
    const n = ordenadas.length;
    const passo = n > 1 ? Math.min((2 * Math.PI) / n, (310 * Math.PI) / 180 / (n - 1)) : 0;
    const angulos = ordenadas.map((_, i) => -Math.PI / 2 + (i - (n - 1) / 2) * passo)
      .sort((a, b) => Math.sin(a) - Math.sin(b));
    ordenadas.forEach((s, i) => {
      const angulo = angulos[i];
      const x = Math.round(rx * Math.cos(angulo));
      const y = Math.round(ry * Math.sin(angulo));
      const atencao = PRECISA_DO_SENHOR.has(s.estado);
      const no = document.createElement("li");
      no.className = "no";
      no.dataset.estado = s.estado;
      no.dataset.atencao = String(atencao);
      if (y < -ry * 0.55) no.classList.add("acima");
      no.style.setProperty("--x", `${x}px`);
      no.style.setProperty("--y", `${y}px`);
      no.style.setProperty("--ordem", i);
      const situacao = [s.rotulo || ROTULO_SESSAO[s.estado] || s.estado, tempoDesde(s.desde_ms)].filter(Boolean).join(", ");
      no.innerHTML = `<span class="nome">${escapar(s.projeto)}</span>` +
        `<span class="situacao">${escapar(situacao)}</span>` +
        (s.mensagem ? `<span class="ultima">${escapar(s.mensagem)}</span>` : "");
      lista.append(no);
      const cx = innerWidth / 2;
      const cy = innerHeight / 2;
      linhas.push(`<line class="${atencao ? "atencao" : ""}" x1="${cx}" y1="${cy}" x2="${cx + x}" y2="${cy + y}"/>`);
    });
    $("ligacoes").innerHTML = linhas.join("");
  }

  // ---------- projetos (todos do Orca, mesmo sem aba aberta) ----------

  function desenharProjetos(itens) {
    const lista = $("lista-projetos");
    lista.replaceChildren();
    itens.forEach((p) => {
      const item = document.createElement("li");
      item.dataset.sessao = p.sessao || "";
      item.dataset.atencao = String(PRECISA_DO_SENHOR.has(p.sessao));
      const situacao = [tempoDesde(p.ts_ms) || "sem atividade",
        p.sessao ? `aba ${ROTULO_SESSAO[p.sessao] || p.sessao}` : p.agente].filter(Boolean).join(" · ");
      item.innerHTML = `<span class="nome">${escapar(p.nome)}</span>` +
        `<span class="situacao">${escapar(situacao)}</span>` +
        ((p.resposta || p.commit) ? `<span class="ultima">${escapar(p.resposta || p.commit)}</span>` : "");
      lista.append(item);
    });
    $("projetos").hidden = itens.length === 0;
  }

  // ---------- confirmações ----------

  function adicionarCartao(evento) {
    if (document.querySelector(`.cartao[data-id="${evento.id}"]`)) return;
    const cartao = document.createElement("div");
    cartao.className = "cartao";
    cartao.dataset.id = evento.id;
    cartao.setAttribute("role", "group");
    const titulo = NOME_PENDENCIA[evento.tipo_pendencia] || "Confirmar";
    const aprovar = evento.tipo_pendencia === "enviar" ? "Enviar" : evento.tipo_pendencia === "lancar" ? "Abrir" : "Aprovar";
    const detalhe = evento.detalhe ? `<pre class="detalhe">${escapar(evento.detalhe)}</pre>` : "";
    cartao.innerHTML = `<h2>${escapar(titulo)}</h2><p>${inline(evento.descricao)}</p>${detalhe}` +
      `<div class="acoes"><button type="button" class="aprovar">${aprovar}</button>` +
      `<button type="button" class="recusar">Cancelar</button></div>`;
    cartao.querySelector(".aprovar").addEventListener("click", () => decidirCartao(evento.id, "aprovar"));
    cartao.querySelector(".recusar").addEventListener("click", () => decidirCartao(evento.id, "recusar"));
    $("cartoes").append(cartao);
  }

  function fimCartao(evento) {
    const cartao = document.querySelector(`.cartao[data-id="${evento.id}"]`);
    if (!cartao) return;
    cartao.dataset.fim = evento.estado;
    setTimeout(() => cartao.remove(), 1200);
  }

  function decidirCartao(id, decisao) {
    if (DEMO) { fimCartao({ id, estado: decisao }); return; }
    enviarAoCerebro("/api/cartao", { id, decisao }).then((r) => {
      // pendência que já expirou ou foi decidida: o cartão sai da tela
      if (r && (r.status === 409 || r.status === 404)) fimCartao({ id, estado: "vencida" });
    });
  }

  // ---------- sistema ----------

  function atualizarRelogio() {
    const agora = new Date();
    $("hora").textContent = agora.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const data = agora.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
    $("data").textContent = data.charAt(0).toUpperCase() + data.slice(1);
  }

  function sistema(evento) {
    if ("voz" in evento) $("servico-voz").dataset.ok = String(evento.voz);
    if ("orca" in evento) $("servico-orca").dataset.ok = String(evento.orca);
    if (evento.clima) $("clima").textContent = evento.clima;
  }

  function definirEstado(valor) {
    document.body.dataset.estado = valor;
    $("estado").textContent = ROTULO_ESTADO[valor] || valor;
    if (valor !== "ouvindo") $("nucleo").style.setProperty("--nivel", 0);
  }

  // ---------- API pública ----------

  function aplicar(evento) {
    switch (evento.tipo) {
      case "estado": definirEstado(evento.valor); break;
      case "nivel": $("nucleo").style.setProperty("--nivel", Math.min(1, evento.valor * 4)); document.body.style.setProperty("--nivel", Math.min(1, evento.valor * 4)); break;
      case "usuario":
        // pergunta feita no meio de uma resposta: a resposta em andamento continua no mesmo balão
        if (!respostaAtual || !respostaAtual.classList.contains("escrevendo")) respostaAtual = null;
        adicionarMensagem("usuario", evento.texto);
        break;
      case "delta": delta(evento.texto); break;
      case "resposta_fim": respostaFim(evento.texto); break;
      case "sessoes": desenharSessoes(evento.itens); break;
      case "projetos": desenharProjetos(evento.itens); break;
      case "cartao": adicionarCartao(evento); break;
      case "cartao_fim": fimCartao(evento); break;
      case "sistema": sistema(evento); break;
      case "historico":
        respostaAtual = null;
        $("cartoes").replaceChildren();
        $("conversa").replaceChildren();
        for (const m of evento.mensagens) adicionarMensagem(m.papel, m.texto);
        break;
      default: break;
    }
  }

  function abrir() {
    document.body.classList.remove("aberto");
    void document.body.offsetWidth; // reinicia a animação de abertura
    document.body.classList.add("aberto");
    $("texto").focus();
  }

  function fechar() {
    document.body.classList.remove("aberto");
    if (!DEMO) enviarAoCerebro("/api/fechar", {});
    const ponte = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.jarvis;
    if (ponte) ponte.postMessage("fechar");
  }

  function enviarAoCerebro(rota, corpo) {
    return fetch(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) })
      .catch(() => null);
  }

  window.jarvis = { abrir, fechar, aplicar };

  // ---------- interação ----------

  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fechar(); });
  $("veu").addEventListener("click", fechar);
  $("entrada").addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = $("texto").value.trim();
    if (!texto) return;
    $("texto").value = "";
    if (DEMO) { demoResponder(texto); return; }
    enviarAoCerebro("/api/mensagem", { texto });
  });
  addEventListener("resize", () => {
    if (ultimasSessoes) desenharSessoes(ultimasSessoes);
  });

  atualizarRelogio();
  setInterval(atualizarRelogio, 15000);

  // ---------- conexão com o cérebro ----------

  function conectar() {
    const fonte = new EventSource("/api/eventos");
    let espera = null;
    fonte.onopen = () => {
      clearTimeout(espera);
      if (document.body.dataset.estado === "desconectado") definirEstado("ocioso");
    };
    fonte.onmessage = (mensagem) => {
      clearTimeout(espera);
      try { aplicar(JSON.parse(mensagem.data)); } catch (_) { /* evento malformado: ignora */ }
    };
    // EventSource reconecta sozinho; se a queda durar mais de 2 s, avisa na tela.
    fonte.onerror = () => {
      clearTimeout(espera);
      espera = setTimeout(() => definirEstado("desconectado"), 2000);
    };
  }

  // ---------- demonstração ----------

  const agora = Date.now();
  const PROJETOS_DEMO = [
    { nome: "jarvis", ts_ms: Date.now() - 2 * 60000, agente: "claude", sessao: "working", resposta: "Montando o painel de projetos" },
    { nome: "app-analise-saude", ts_ms: Date.now() - 32 * 3600000, agente: "claude", sessao: "", resposta: "Mesclei o Plano 4 (memória) na master e enviei ao GitHub." },
    { nome: "lorenzo-portfolio", ts_ms: Date.now() - 4 * 86400000, agente: "claude", sessao: "", resposta: "Cadeia de 4 portões, do commit ao ar." },
    { nome: "gestao-postos", ts_ms: Date.now() - 13 * 86400000, agente: "codex", sessao: "", resposta: "A Fase 3 é o portal do candidato." },
    { nome: "hostinger-sv", ts_ms: Date.now() - 6 * 86400000, agente: "claude", sessao: "done", resposta: "Escalabilidade: mesmo desenho do Swarm." },
  ];
  const SESSOES_DEMO = [
    { projeto: "app-analise-saude", estado: "waiting", desde_ms: agora - 3 * 60000, mensagem: "Posso seguir com o Plano 5 (notificações)?" },
    { projeto: "dailytracker-app", estado: "working", desde_ms: agora - 7 * 60000, mensagem: "Rodando a suíte de testes do módulo de metas" },
    { projeto: "hostinger-sv", estado: "done", desde_ms: agora - 139 * 3600000, mensagem: "Escalabilidade: mesmo desenho do Swarm" },
    { projeto: "lorenzo-portfolio", estado: "permission", desde_ms: agora - 60000, mensagem: "Quer rodar npm run build" },
    { projeto: "jarvis", estado: "working", desde_ms: agora - 12 * 60000, mensagem: "Montando a janela do Jarvis" },
  ];
  const RESPOSTA_DEMO = "Dois agentes precisam do senhor.\n\n" +
    "- **app-analise-saude** terminou o Plano 4 e pergunta se pode seguir com o Plano 5.\n" +
    "- **lorenzo-portfolio** pede permissão para rodar `npm run build`.\n\n" +
    "O dailytracker está rodando os testes e o hostinger está parado desde a semana passada.\n" +
    "🔊 Dois agentes precisam do senhor: o de saúde quer seguir com o plano cinco e o portfólio pede para rodar o build.";

  function demoQuadroFinal() {
    aplicar({ tipo: "sistema", voz: true, orca: true, clima: "16 °C, nublado em São Paulo" });
    aplicar({ tipo: "sessoes", itens: SESSOES_DEMO });
    aplicar({ tipo: "projetos", itens: PROJETOS_DEMO });
    aplicar({ tipo: "historico", mensagens: [
      { papel: "usuario", texto: "Bom dia, Jarvis." },
      { papel: "jarvis", texto: "Bom dia, senhor. Estão fazendo 16 graus e o céu está nublado." },
      { papel: "usuario", texto: "Jarvis, como estão os projetos?" },
      { papel: "jarvis", texto: RESPOSTA_DEMO },
    ] });
    aplicar({ tipo: "cartao", id: 7, tipo_pendencia: "enviar", descricao: "Para **app-analise-saude**: «Pode seguir com o Plano 5.»" });
    definirEstado(parametros.get("estado") || "falando");
  }

  function demoResponder(texto) {
    aplicar({ tipo: "usuario", texto });
    definirEstado("pensando");
    setTimeout(() => {
      definirEstado("falando");
      const pedacos = RESPOSTA_DEMO.match(/.{1,14}/gs);
      pedacos.forEach((p, i) => setTimeout(() => aplicar({ tipo: "delta", texto: p }), i * 45));
      setTimeout(() => { aplicar({ tipo: "resposta_fim", texto: RESPOSTA_DEMO }); definirEstado("ocioso"); },
        pedacos.length * 45 + 400);
    }, 1400);
  }

  function demoAoVivo() {
    aplicar({ tipo: "sistema", voz: true, orca: true, clima: "16 °C, nublado em São Paulo" });
    aplicar({ tipo: "sessoes", itens: SESSOES_DEMO });
    aplicar({ tipo: "projetos", itens: PROJETOS_DEMO });
    aplicar({ tipo: "historico", mensagens: [
      { papel: "usuario", texto: "Bom dia, Jarvis." },
      { papel: "jarvis", texto: "Bom dia, senhor. Estão fazendo 16 graus e o céu está nublado." },
    ] });
    definirEstado("ouvindo");
    let t = 0;
    const respiracao = setInterval(() => {
      t += 1;
      aplicar({ tipo: "nivel", valor: Math.abs(Math.sin(t / 3)) * 0.12 + Math.random() * 0.05 });
    }, 90);
    setTimeout(() => {
      clearInterval(respiracao);
      demoResponder("Jarvis, como estão os projetos?");
      setTimeout(() => aplicar({ tipo: "cartao", id: 7, tipo_pendencia: "enviar",
        descricao: "Para **app-analise-saude**: «Pode seguir com o Plano 5.»" }), 6500);
    }, 3200);
  }

  if (DEMO) {
    if (parametros.has("fundo")) document.documentElement.classList.add("fundo-teste");
    if (parametros.has("sessoes")) SESSOES_DEMO.splice(Number(parametros.get("sessoes")));
    if (parametros.has("quadro")) demoQuadroFinal(); else demoAoVivo();
    abrir();
  } else {
    conectar();
  }
})();
