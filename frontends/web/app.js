/* ============================================================
   app.js — lógica da interface da Alice
   (chat SSE, markdown + código destacado, conversas, memória, config)
   ============================================================ */
'use strict';

const $ = id => document.getElementById(id);
const log = $('log'), entrada = $('entrada'), btnEnviar = $('enviar');
const temp = $('temp'), tempval = $('tempval');
let es = null, estado = {};

/* ---------------------------------------------------------- utilidades */
function abre(id) { $(id).classList.add('on'); }
function fecha(id) { $(id).classList.remove('on'); }
document.querySelectorAll('[data-fecha]').forEach(b => b.onclick = () => fecha(b.dataset.fecha));
document.querySelectorAll('.overlay').forEach(ov =>
  ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('on'); }));

function post(url, obj) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(obj) }).then(r => r.json());
}
const pertoDoFim = () => log.scrollHeight - log.scrollTop - log.clientHeight < 140;
function rolar(forca) { if (forca || pertoDoFim()) log.scrollTop = log.scrollHeight; }
function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---------------------------------------------------------- naipes de fundo */
(function naipes() {
  const alvo = $('naipes'), simbolos = ['♥', '♠', '♦', '♣'];
  for (let i = 0; i < 14; i++) {
    const s = document.createElement('span');
    s.textContent = simbolos[i % 4];
    if (i % 4 === 0 || i % 4 === 2) s.className = 'copas';
    s.style.setProperty('--x', (Math.random() * 100).toFixed(1) + '%');
    s.style.setProperty('--tam', (1.1 + Math.random() * 2.4).toFixed(2) + 'rem');
    s.style.setProperty('--dur', (46 + Math.random() * 70).toFixed(0) + 's');
    s.style.setProperty('--del', (-Math.random() * 90).toFixed(0) + 's');
    alvo.appendChild(s);
  }
})();

/* ============================================================
   destaque de sintaxe (leve, feito em casa)
   ============================================================ */
const KW = {
  gdscript: 'func var const signal extends class_name enum if elif else for while match when break continue pass return await and or not in is as static super self void',
  python: 'def class return if elif else for while break continue pass import from as with try except finally raise lambda global nonlocal yield async await and or not in is None True False self',
  javascript: 'function const let var return if else for while break continue class extends new this typeof instanceof async await import export default try catch finally throw switch case null undefined true false',
  json: '',
};
KW.js = KW.javascript; KW.py = KW.python; KW.gd = KW.gdscript;

function destacar(codigo, lang) {
  const kws = new Set((KW[lang] || KW.gdscript).split(' ').filter(Boolean));
  let out = '', i = 0;
  const n = codigo.length;
  const push = (txt, cls) => { out += cls ? `<span class="${cls}">${esc(txt)}</span>` : esc(txt); };
  while (i < n) {
    const c = codigo[i];
    if (c === '#' && lang !== 'javascript' && lang !== 'js') {          // comentário
      const fim = codigo.indexOf('\n', i); const j = fim === -1 ? n : fim;
      push(codigo.slice(i, j), 'tok-com'); i = j; continue;
    }
    if ((c === '/' && codigo[i + 1] === '/') && (lang === 'javascript' || lang === 'js')) {
      const fim = codigo.indexOf('\n', i); const j = fim === -1 ? n : fim;
      push(codigo.slice(i, j), 'tok-com'); i = j; continue;
    }
    if (c === '"' || c === "'") {                                        // string
      let j = i + 1;
      while (j < n && codigo[j] !== c) { if (codigo[j] === '\\') j++; j++; }
      push(codigo.slice(i, Math.min(j + 1, n)), 'tok-str'); i = j + 1; continue;
    }
    if (c === '@' || c === '$' || (c === '%' && /\w/.test(codigo[i + 1] || ''))) { // @anota / $No
      let j = i + 1; while (j < n && /[\w/]/.test(codigo[j])) j++;
      push(codigo.slice(i, j), 'tok-ann'); i = j; continue;
    }
    if (/\d/.test(c) && !/\w/.test(codigo[i - 1] || '')) {               // número
      let j = i; while (j < n && /[\d._xa-fA-F]/.test(codigo[j])) j++;
      push(codigo.slice(i, j), 'tok-num'); i = j; continue;
    }
    if (/[A-Za-z_]/.test(c)) {                                           // palavra
      let j = i; while (j < n && /\w/.test(codigo[j])) j++;
      const w = codigo.slice(i, j);
      if (kws.has(w)) push(w, 'tok-kw');
      else if (/^[A-Z][A-Z0-9_]+$/.test(w)) push(w, 'tok-cte');          // CONSTANTE
      else if (/^[A-Z]/.test(w)) push(w, 'tok-ty');                       // Tipo/Classe
      else if (codigo[j] === '(') push(w, 'tok-fn');                      // chamada()
      else push(w);
      i = j; continue;
    }
    push(c); i++;
  }
  return out;
}

/* ============================================================
   markdown (renderizador pequeno e suficiente)
   ============================================================ */
function inline(t) {
  let s = esc(t);
  s = s.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function renderMd(texto) {
  const linhas = texto.split('\n');
  let html = '', i = 0, paragrafo = [];
  const fechaP = () => {
    if (paragrafo.length) { html += `<p>${inline(paragrafo.join('\n')).replace(/\n/g, '<br>')}</p>`; paragrafo = []; }
  };
  while (i < linhas.length) {
    const l = linhas[i];
    const cerca = l.match(/^```(\w*)\s*$/);
    if (cerca) {                                       // bloco de código
      fechaP();
      const lang = (cerca[1] || 'gdscript').toLowerCase();
      const corpo = [];
      i++;
      while (i < linhas.length && !/^```\s*$/.test(linhas[i])) corpo.push(linhas[i++]);
      i++; // pula o fechamento (ou o fim, se stream ainda não fechou)
      const cod = corpo.join('\n');
      html += `<div class="cod"><div class="cab"><span class="lang">${esc(lang)}</span>` +
        `<button class="copiar" data-cod="${encodeURIComponent(cod)}">⧉ copiar</button></div>` +
        `<pre><code class="bloco">${destacar(cod, lang)}</code></pre></div>`;
      continue;
    }
    const h = l.match(/^(#{1,3})\s+(.*)/);
    if (h) { fechaP(); html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i++; continue; }
    if (/^\s*([-*+]|\d+\.)\s+/.test(l)) {              // lista
      fechaP();
      const ordenada = /^\s*\d+\./.test(l);
      let itens = '';
      while (i < linhas.length && /^\s*([-*+]|\d+\.)\s+/.test(linhas[i])) {
        itens += `<li>${inline(linhas[i].replace(/^\s*([-*+]|\d+\.)\s+/, ''))}</li>`;
        i++;
      }
      html += ordenada ? `<ol>${itens}</ol>` : `<ul>${itens}</ul>`;
      continue;
    }
    if (/^>\s?/.test(l)) {                             // citação
      fechaP();
      const cit = [];
      while (i < linhas.length && /^>\s?/.test(linhas[i])) cit.push(linhas[i++].replace(/^>\s?/, ''));
      html += `<blockquote>${inline(cit.join('\n')).replace(/\n/g, '<br>')}</blockquote>`;
      continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(l)) { fechaP(); html += '<hr>'; i++; continue; }
    if (l.includes('|') && linhas[i + 1] && /^\s*\|?[\s|:-]+\|?\s*$/.test(linhas[i + 1])
        && linhas[i + 1].includes('-')) {              // tabela
      fechaP();
      const celulas = s => s.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(x => x.trim());
      let th = '<tr>' + celulas(l).map(c => `<th>${inline(c)}</th>`).join('') + '</tr>';
      i += 2;
      let corpo = '';
      while (i < linhas.length && linhas[i].includes('|')) {
        corpo += '<tr>' + celulas(linhas[i]).map(c => `<td>${inline(c)}</td>`).join('') + '</tr>';
        i++;
      }
      html += `<table><thead>${th}</thead><tbody>${corpo}</tbody></table>`;
      continue;
    }
    if (!l.trim()) { fechaP(); i++; continue; }
    paragrafo.push(l); i++;
  }
  fechaP();
  return html;
}

log.addEventListener('click', e => {                    // copiar código
  const b = e.target.closest('.copiar');
  if (!b) return;
  navigator.clipboard.writeText(decodeURIComponent(b.dataset.cod)).then(() => {
    b.textContent = '✓ copiado';
    setTimeout(() => { b.textContent = '⧉ copiar'; }, 1400);
  });
});

/* ============================================================
   montagem de mensagens
   ============================================================ */
function tiraBoasVindas() { const b = $('boasVindas'); if (b) b.remove(); }

function avatarMini() {
  const d = document.createElement('div');
  d.className = 'mini-alice';
  d.innerHTML = '<span class="ini">A</span><img src="/avatar" alt="" onerror="this.remove()">';
  return d;
}

function msgUsuario(texto) {
  tiraBoasVindas();
  const row = document.createElement('div');
  row.className = 'row u';
  row.innerHTML = '<div class="corpo"><div class="msg"></div></div>';
  row.querySelector('.msg').textContent = texto;
  log.appendChild(row); rolar(true);
}

function msgAlice() {
  tiraBoasVindas();
  const row = document.createElement('div');
  row.className = 'row a';
  row.appendChild(avatarMini());
  const corpo = document.createElement('div');
  corpo.className = 'corpo';
  corpo.innerHTML = '<div class="autor">alice</div><div class="msg"><div class="md"></div></div>';
  row.appendChild(corpo);
  log.appendChild(row); rolar(true);
  const md = corpo.querySelector('.md');
  md._bruto = '';
  return md;
}

function chipTool(nome, args, girando) {
  tiraBoasVindas();
  const c = document.createElement('div');
  c.className = 'tool-chip' + (girando ? '' : ' parada');
  const resumo = args ? `${nome}(${args})` : nome;
  c.innerHTML = `<span class="eng">⚙</span><span class="args"></span>`;
  c.querySelector('.args').textContent = resumo;
  c.title = resumo;
  log.appendChild(c); rolar();
  return c;
}

function mostrarImg(url) {
  tiraBoasVindas();
  const w = document.createElement('div');
  w.className = 'shot';
  w.innerHTML = '<div class="cap">📸 o jogo, visto pelos olhos dela</div><img>';
  const img = w.querySelector('img');
  img.src = url; img.onload = () => rolar();
  log.appendChild(w); rolar();
}

function chipErro(txt) {
  const c = document.createElement('div');
  c.className = 'erro-chip';
  c.textContent = '⚠ ' + txt;
  log.appendChild(c); rolar();
}

function indicadorDigitando() {
  const md = msgAlice();
  md.innerHTML = '<span class="digitando"><i></i><i></i><i></i></span>';
  md._digitando = true;
  return md;
}

/* ============================================================
   fluxo do chat (SSE)
   ============================================================ */
function enviar(msgPronta) {
  const msg = (msgPronta || entrada.value).trim();
  if (!msg || btnEnviar.disabled) return;
  msgUsuario(msg);
  entrada.value = ''; entrada.style.height = 'auto';
  btnEnviar.disabled = true; entrada.disabled = true;

  let alvo = indicadorDigitando();
  let chipAtivo = null;

  const paraChip = () => { if (chipAtivo) { chipAtivo.classList.add('parada'); chipAtivo = null; } };
  const encerra = () => {
    paraChip();
    if (alvo && alvo._digitando) alvo.closest('.row').remove();
    if (es) { es.close(); es = null; }
    btnEnviar.disabled = false; entrada.disabled = false; entrada.focus();
    carregarConversas();
  };

  es = new EventSource('/chat?msg=' + encodeURIComponent(msg));
  es.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'text') {
      paraChip();
      if (!alvo) alvo = msgAlice();
      if (alvo._digitando) { alvo._digitando = false; alvo.innerHTML = ''; }
      alvo._bruto += d.data;
      alvo.innerHTML = renderMd(alvo._bruto);
      rolar();
    } else if (d.type === 'tool') {
      paraChip();
      if (alvo && alvo._digitando) { alvo.closest('.row').remove(); }
      alvo = null;
      const par = d.data.match(/^([\w]+)\((.*)\)$/s);
      chipAtivo = chipTool(par ? par[1] : d.data, par ? par[2] : '', true);
    } else if (d.type === 'image') {
      paraChip(); mostrarImg(d.data);
    } else if (d.type === 'error') {
      chipErro(d.data);
    } else if (d.type === 'done') {
      encerra();
    }
  };
  es.onerror = () => encerra();
}

btnEnviar.onclick = () => enviar();
entrada.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
});
entrada.addEventListener('input', () => {
  entrada.style.height = 'auto';
  entrada.style.height = Math.min(entrada.scrollHeight, 176) + 'px';
});
document.querySelectorAll('.sugestao').forEach(b => b.onclick = () => enviar(b.dataset.msg));

/* ============================================================
   estado, conversas, histórico
   ============================================================ */
async function carregarEstado() {
  estado = await (await fetch('/state')).json();
  $('rodapeModelo').textContent = estado.model;
  temp.value = estado.temperature;
  tempval.textContent = (+estado.temperature).toFixed(2);
}

async function carregarConversas() {
  const lista = await (await fetch('/conversas')).json();
  const box = $('convs'); box.innerHTML = '';
  for (const c of lista) {
    const d = document.createElement('div');
    d.className = 'conv' + (c.id === estado.conv_atual ? ' ativa' : '');
    d.innerHTML = '<span class="x">✕</span><div class="t"></div><div class="d"></div>';
    d.querySelector('.t').textContent = c.titulo;
    d.querySelector('.d').textContent = c.atualizado;
    d.onclick = e => { if (!e.target.classList.contains('x')) abrirConversa(c.id); };
    d.querySelector('.x').onclick = async e => {
      e.stopPropagation();
      await post('/apagar', { id: c.id });
      if (c.id === estado.conv_atual) await novaConversa(); else carregarConversas();
    };
    box.appendChild(d);
  }
}

async function abrirConversa(id) {
  const d = await (await fetch('/conversa?id=' + encodeURIComponent(id))).json();
  estado.conv_atual = id; log.innerHTML = '';
  for (const m of d.messages) {
    if (m.role === 'user') msgUsuario(m.content);
    else if (m.role === 'assistant' && m.content) {
      const md = msgAlice(); md._bruto = m.content; md.innerHTML = renderMd(m.content);
    } else if (m.role === 'tool') chipTool(m.tool_name || 'tool', '', false);
  }
  rolar(true);
  carregarConversas();
}

async function novaConversa() {
  const r = await post('/nova', {});
  estado.conv_atual = r.id; log.innerHTML = '';
  carregarConversas();
}
$('novaConversa').onclick = novaConversa;

/* ---------------------------------------------------------- temperatura */
temp.addEventListener('input', () => tempval.textContent = (+temp.value).toFixed(2));
temp.addEventListener('change', () => post('/config', { temperature: +temp.value }).then(carregarEstado));

/* ---------------------------------------------------------- config */
$('btnCfg').onclick = () => {
  $('c_model').value = estado.model; $('c_temp').value = estado.temperature;
  $('c_ctx').value = estado.num_ctx; $('c_host').value = estado.ollama_host;
  $('c_wd').value = estado.workdir; $('c_godot').value = estado.godot_bin;
  $('c_ref').value = estado.pasta_referencia || '';
  abre('ovCfg');
};
$('salvarCfg').onclick = async () => {
  await post('/config', {
    model: $('c_model').value.trim(), temperature: +$('c_temp').value,
    num_ctx: +$('c_ctx').value, ollama_host: $('c_host').value.trim(),
    workdir: $('c_wd').value.trim(), godot_bin: $('c_godot').value.trim(),
    pasta_referencia: $('c_ref').value.trim(),
  });
  await carregarEstado(); fecha('ovCfg');
};

/* ---------------------------------------------------------- memória */
$('btnMem').onclick = async () => { await pintarMemoria(); abre('ovMem'); };
async function pintarMemoria() {
  const fatos = await (await fetch('/memoria')).json();
  const box = $('fatos'); box.innerHTML = '';
  if (!fatos.length) {
    box.innerHTML = '<p class="text-apagado text-[.84rem]">(vazio — ela ainda não guardou nada permanente)</p>';
  }
  fatos.forEach((f, i) => {
    const d = document.createElement('div');
    d.className = 'fato';
    d.innerHTML = '<div class="txt"><div class="tag"></div><div class="c"></div></div><span class="del">🗑</span>';
    d.querySelector('.tag').textContent = f.tag || 'geral';
    d.querySelector('.c').textContent = f.texto;
    d.querySelector('.del').onclick = async () => { await post('/memoria_del', { indice: i }); pintarMemoria(); };
    box.appendChild(d);
  });
}
$('addFato').onclick = async () => {
  const t = $('m_txt').value.trim(); if (!t) return;
  await post('/memoria_add', { texto: t, tag: $('m_tag').value.trim() || 'geral' });
  $('m_txt').value = ''; $('m_tag').value = '';
  pintarMemoria();
};

/* ---------------------------------------------------------- monitor de atividade */
const statusPill = $('statusPill'), statusTxt = $('statusTxt'), ativPanel = $('ativPanel');
const rotulos = { ociosa: 'ociosa', pensando: 'pensando…', escrevendo: 'escrevendo…', ferramenta: 'trabalhando' };
statusPill.onclick = () => ativPanel.classList.toggle('hidden');
async function poll() {
  try {
    const a = await (await fetch('/atividade')).json();
    const ativa = a.status !== 'ociosa';
    statusPill.className = 'pilula ' + (ativa ? 'ativa' : 'ociosa');
    let txt = rotulos[a.status] || a.status;
    if (a.status === 'ferramenta' && a.detalhe) txt = '⚙ ' + a.detalhe;
    if (ativa) { txt += ' · ' + a.ha_seg + 's'; if (a.origem) txt += ' (' + a.origem + ')'; }
    statusTxt.textContent = txt;
    ativPanel.innerHTML = (a.log || []).map(e =>
      `<div class="ev">${e.t} <b>${esc(e.status)}</b> ${esc(e.detalhe || '')} ${e.origem ? '· ' + esc(e.origem) : ''}</div>`
    ).join('') || '<div class="ev">(sem atividade ainda)</div>';
  } catch {
    statusPill.className = 'pilula ociosa';
    statusTxt.textContent = 'servidor off?';
  }
}
setInterval(poll, 1200); poll();

/* ---------------------------------------------------------- boot */
(async () => { await carregarEstado(); await carregarConversas(); entrada.focus(); })();
