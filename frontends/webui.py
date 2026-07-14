# ============================================================
#  frontends/webui.py — Alice numa interface visual completa (navegador),
#  servida 100% pela biblioteca padrão do Python (sem dependência nova).
#
#  Rodar (de dentro da pasta Alice):
#      python -m frontends.webui [porta]     # padrão 7861
#
#  Recursos:
#   • Chat com streaming e ferramentas aparecendo ao vivo
#   • HISTÓRICO persistente: conversas salvas em disco, retomáveis (sidebar)
#   • MEMÓRIA DE LONGO PRAZO: fatos que a Alice acumula e "fica mais inteligente"
#   • CONFIGURAÇÃO pela própria interface (modelo, temperatura, projeto, Godot…)
#
#  Uso local single-user (só você): escuta em 127.0.0.1, ferramentas completas.
# ============================================================
import os
import sys
import json
import threading
import webbrowser
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config, build_system_prompt, CONFIG_JSON
from core.agent import Agent
from core import tools, memory, longmemory

# ------------------------------------------------------------------ estado
import time
from collections import deque

cfg = load_config()
tools.configure(workdir=cfg.workdir, confirm_cb=None, godot_bin=cfg.godot_bin,
                reference_dir=cfg.pasta_referencia)
alice = Agent(cfg, build_system_prompt(cfg))
conv_atual = memory.novo_id()          # id da conversa em andamento
_lock = threading.Lock()               # uma geração por vez

# foto da Alice (avatar); coloque um alice.png aqui que a interface exibe
AVATAR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "alice.png")

# ---- monitor de atividade (pra você VER que ela está trabalhando) --------
_atividade = {"status": "ociosa", "detalhe": "", "desde": time.time(), "origem": ""}
_ativ_log = deque(maxlen=40)


def _atv(status: str, detalhe: str = "", origem: str = ""):
    _atividade["status"] = status
    _atividade["detalhe"] = detalhe
    _atividade["desde"] = time.time()
    if origem:
        _atividade["origem"] = origem
    if status != "ociosa":
        _ativ_log.appendleft({"t": time.strftime("%H:%M:%S"),
                              "status": status, "detalhe": detalhe,
                              "origem": _atividade["origem"]})


def _resumo_tool(dado) -> str:
    nome, args = dado
    resumo = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
    return f"{nome}({resumo})"


# ---- helpers de estado --------------------------------------------------
def _estado() -> dict:
    return {
        "model": cfg.model, "temperature": cfg.temperature, "num_ctx": cfg.num_ctx,
        "ollama_host": cfg.ollama_host, "workdir": os.path.abspath(cfg.workdir),
        "godot_bin": cfg.godot_bin, "conv_atual": conv_atual,
        "pasta_referencia": cfg.pasta_referencia,
    }


def _reconstruir_prompt():
    """Atualiza o system prompt (projeto/memória) preservando o histórico."""
    alice.messages[0] = {"role": "system", "content": build_system_prompt(cfg)}


def _salvar_config(mudancas: dict):
    campos = {"model", "temperature", "num_ctx", "ollama_host", "workdir",
              "godot_bin", "confirm_commands", "pasta_referencia"}
    aplicadas = {}
    for k, v in mudancas.items():
        if k not in campos:
            continue
        if k in ("temperature",):
            v = float(v)
        elif k in ("num_ctx",):
            v = int(v)
        elif k in ("confirm_commands",):
            v = bool(v)
        setattr(cfg, k, v)
        aplicadas[k] = v
    # reconfigura as "mãos" (workdir/godot podem ter mudado)
    tools.configure(workdir=cfg.workdir, confirm_cb=None, godot_bin=cfg.godot_bin,
                    reference_dir=cfg.pasta_referencia)
    _reconstruir_prompt()
    # persiste no config.json
    try:
        with open(CONFIG_JSON, encoding="utf-8") as f:
            data = json.load(f)
        data.update(aplicadas)
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("aviso: não salvou config.json:", e)


def _salvar_conversa_atual():
    corpo = alice.messages[1:]  # tudo menos o system prompt
    if corpo:
        memory.salvar_conversa(conv_atual, corpo)


# ------------------------------------------------------------------ HTML
PAGINA = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alice</title>
<style>
  /* ===== Tema "Alice no País das Maravilhas" ===== */
  :root{
    --bg:#0b1030; --bg2:#0a0d26;
    --panel:#111a44; --panel2:#1a2660; --panel3:#243172;
    --txt:#eef2ff; --dim:#93a2d6;
    --accent:#5b8de0;            /* azul cornflower do vestido */
    --accent2:#7aa8f0;
    --gold:#e7c766; --gold2:#f3dc93;   /* cabelo / relógio */
    --cream:#f4ecd6;             /* avental */
    --heart:#e05673;            /* cartas de copas */
    --user:#274088;              /* balão do usuário */
    --tool:#12324a;
    --line:rgba(231,199,102,.16); /* fio dourado */
    --line2:rgba(122,168,240,.16);
    --danger:#e05673;
    --serif:Georgia,'Iowan Old Style','Times New Roman',serif;
  }
  *{ box-sizing:border-box; }
  html,body{ margin:0; height:100%; }
  ::selection{ background:rgba(231,199,102,.3); }
  body{ display:flex; font-family:system-ui,Segoe UI,Roboto,sans-serif; color:var(--txt);
        height:100vh; overflow:hidden;
        background:
          radial-gradient(1100px 620px at 82% -12%, rgba(91,141,224,.22), transparent 60%),
          radial-gradient(820px 520px at -5% 112%, rgba(231,199,102,.12), transparent 62%),
          linear-gradient(158deg, var(--bg), var(--bg2)); }
  /* barras de rolagem discretas */
  *::-webkit-scrollbar{ width:9px; height:9px; }
  *::-webkit-scrollbar-thumb{ background:rgba(122,168,240,.25); border-radius:10px; }
  *::-webkit-scrollbar-thumb:hover{ background:rgba(231,199,102,.4); }

  /* -------- sidebar -------- */
  #sidebar{ width:262px; background:linear-gradient(180deg, rgba(17,26,68,.92), rgba(10,13,38,.92));
            border-right:1px solid var(--line); display:flex; flex-direction:column; flex-shrink:0;
            backdrop-filter:blur(4px); }
  #sidebar .topo{ padding:16px 14px; border-bottom:1px solid var(--line); }
  .marca{ display:flex; align-items:center; gap:12px; margin-bottom:14px; }
  .foto{ position:relative; width:52px; height:52px; border-radius:50%; flex-shrink:0;
         background:radial-gradient(circle at 35% 30%, var(--gold2), #b98f38);
         box-shadow:0 0 0 2px var(--gold), 0 0 18px rgba(231,199,102,.4); overflow:hidden; }
  .foto .ini{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
              font-family:var(--serif); font-size:1.7rem; font-weight:700; color:#3a2a08; }
  .foto img{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .marca .nome{ font-family:var(--serif); font-size:1.5rem; font-weight:700; letter-spacing:.5px;
                background:linear-gradient(90deg, var(--gold2), var(--gold)); -webkit-background-clip:text;
                background-clip:text; color:transparent; line-height:1; }
  .marca .suits{ display:block; font-size:.72rem; letter-spacing:3px; margin-top:3px;
                 color:var(--accent2); }
  .marca .suits .h{ color:var(--heart); }
  #novaConversa{ width:100%; background:linear-gradient(180deg, var(--gold2), var(--gold));
                 color:#3a2a08; border:none; border-radius:11px; padding:11px; font-weight:700;
                 cursor:pointer; font-size:.9rem; box-shadow:0 3px 12px rgba(231,199,102,.25);
                 transition:transform .1s, box-shadow .2s; }
  #novaConversa:hover{ transform:translateY(-1px); box-shadow:0 5px 16px rgba(231,199,102,.4); }
  #convs{ flex:1; overflow-y:auto; padding:8px; }
  .conv{ padding:9px 11px; border-radius:9px; cursor:pointer; margin-bottom:4px; font-size:.86rem;
         display:flex; flex-direction:column; gap:2px; border:1px solid transparent; }
  .conv:hover{ background:rgba(122,168,240,.08); }
  .conv.ativa{ background:rgba(91,141,224,.14); border-color:var(--line); }
  .conv .t{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .conv .d{ font-size:.7rem; color:var(--dim); }
  .conv .x{ float:right; color:var(--dim); font-size:.9rem; opacity:0; }
  .conv:hover .x{ opacity:1; }
  .conv .x:hover{ color:var(--danger); }

  /* -------- área principal -------- */
  #main{ flex:1; display:flex; flex-direction:column; min-width:0; }
  header{ display:flex; align-items:center; gap:14px; padding:11px 18px;
          background:linear-gradient(180deg, rgba(17,26,68,.7), rgba(17,26,68,.35));
          border-bottom:1px solid var(--line); flex-wrap:wrap;
          box-shadow:0 1px 0 rgba(122,168,240,.08); }
  header .titulo{ font-family:var(--serif); font-weight:700; font-size:1.35rem; letter-spacing:.5px;
                  background:linear-gradient(90deg, var(--gold2), var(--gold)); -webkit-background-clip:text;
                  background-clip:text; color:transparent; }
  header .dim{ color:var(--dim); font-size:.8rem; }
  header .grupo{ display:flex; align-items:center; gap:8px; }
  header input[type=range]{ accent-color:var(--gold); }
  .btn{ background:rgba(122,168,240,.1); color:var(--txt); border:1px solid var(--line);
        border-radius:9px; padding:7px 12px; font-size:.82rem; cursor:pointer; transition:.15s; }
  .btn:hover{ border-color:var(--gold); background:rgba(231,199,102,.12); }

  /* -------- indicador de atividade -------- */
  .pill{ display:flex; align-items:center; gap:7px; padding:5px 12px; border-radius:20px;
         font-size:.8rem; cursor:pointer; border:1px solid var(--line); user-select:none; }
  .pill .ponto{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }
  .pill.ociosa{ color:var(--dim); } .pill.ociosa .ponto{ background:#5a6698; }
  .pill.ativa{ color:var(--gold2); border-color:rgba(231,199,102,.4);
               background:rgba(231,199,102,.12); }
  .pill.ativa .ponto{ background:var(--gold); box-shadow:0 0 8px var(--gold); animation:pulse 1s infinite; }
  @keyframes pulse{ 0%,100%{ opacity:1; } 50%{ opacity:.25; } }
  #ativPanel{ display:none; background:rgba(10,13,38,.6); border-bottom:1px solid var(--line);
              max-height:180px; overflow-y:auto; padding:8px 18px; font-family:ui-monospace,monospace;
              font-size:.76rem; }
  #ativPanel.aberto{ display:block; }
  #ativPanel .ev{ padding:2px 0; color:var(--dim); }
  #ativPanel .ev b{ color:var(--gold2); font-weight:600; }

  #log{ flex:1; overflow-y:auto; padding:24px; display:flex; flex-direction:column; gap:15px; }
  .row{ display:flex; flex-direction:column; }
  .row.u{ align-items:flex-end; } .row.a{ align-items:flex-start; }
  .msg{ max-width:82%; padding:12px 15px; border-radius:15px; white-space:pre-wrap;
        word-wrap:break-word; line-height:1.55; font-size:.95rem; box-shadow:0 2px 10px rgba(0,0,0,.2); }
  .u .msg{ background:linear-gradient(180deg, var(--user), #1d3068); border:1px solid var(--line2);
           border-bottom-right-radius:4px; }
  .a .msg{ background:linear-gradient(180deg, var(--panel2), var(--panel)); border:1px solid var(--line);
           border-bottom-left-radius:4px; }
  .tool{ align-self:flex-start; background:rgba(122,168,240,.1); color:var(--accent2);
         border:1px solid var(--line2); font-family:ui-monospace,monospace;
         font-size:.78rem; padding:6px 11px; border-radius:9px; max-width:82%; }
  .autor{ font-size:.72rem; color:var(--gold); font-family:var(--serif); font-style:italic;
          margin:0 8px 4px; }
  .shot{ align-self:flex-start; max-width:82%; }
  .shot .cap{ font-size:.72rem; color:var(--dim); margin:0 4px 5px; }
  .shot img{ max-width:100%; border-radius:12px; border:2px solid var(--gold); display:block;
             box-shadow:0 4px 20px rgba(231,199,102,.2); }
  footer{ display:flex; gap:10px; padding:15px 18px;
          background:linear-gradient(180deg, rgba(17,26,68,.35), rgba(17,26,68,.7));
          border-top:1px solid var(--line); }
  #entrada{ flex:1; resize:none; background:rgba(10,13,38,.55); color:var(--txt);
            border:1px solid var(--line2); border-radius:12px; padding:12px 14px; font-size:.95rem;
            font-family:inherit; max-height:170px; transition:border-color .15s; }
  #entrada:focus{ outline:none; border-color:var(--gold); }
  #enviar{ background:linear-gradient(180deg, var(--gold2), var(--gold)); color:#3a2a08; border:none;
           border-radius:12px; padding:0 24px; font-weight:700; cursor:pointer; font-size:.95rem;
           box-shadow:0 3px 12px rgba(231,199,102,.25); transition:transform .1s; }
  #enviar:hover:not(:disabled){ transform:translateY(-1px); }
  #enviar:disabled{ opacity:.45; cursor:default; }
  .piscando::after{ content:"▋"; animation:blink 1s steps(2) infinite; color:var(--gold); }
  @keyframes blink{ 50%{ opacity:0; } }

  /* -------- modais -------- */
  .overlay{ position:fixed; inset:0; background:rgba(6,9,26,.68); display:none;
            align-items:center; justify-content:center; z-index:10; backdrop-filter:blur(3px); }
  .overlay.on{ display:flex; }
  .modal{ background:linear-gradient(160deg, var(--panel), var(--bg2));
          border:1px solid var(--line); border-radius:16px; width:min(560px,92vw);
          max-height:86vh; overflow-y:auto; padding:24px; box-shadow:0 20px 60px rgba(0,0,0,.5); }
  .modal h2{ margin:0 0 16px; font-size:1.25rem; font-family:var(--serif); color:var(--gold2); }
  .campo{ margin-bottom:14px; }
  .campo label{ display:block; font-size:.8rem; color:var(--dim); margin-bottom:5px; }
  .campo input[type=text], .campo input[type=number]{ width:100%; background:rgba(10,13,38,.55); color:var(--txt);
          border:1px solid var(--line2); border-radius:9px; padding:10px 12px; font-size:.9rem; }
  .campo input:focus{ outline:none; border-color:var(--gold); }
  .campo.linha{ display:flex; align-items:center; gap:8px; }
  .modal .rodape{ display:flex; justify-content:flex-end; gap:10px; margin-top:8px; }
  .fato{ background:rgba(10,13,38,.5); border:1px solid var(--line); border-radius:9px; padding:10px 12px;
         margin-bottom:8px; display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
  .fato .tag{ font-size:.68rem; color:var(--gold); text-transform:uppercase; letter-spacing:.5px; }
  .fato .txt{ font-size:.88rem; flex:1; }
  .fato .del{ color:var(--dim); cursor:pointer; } .fato .del:hover{ color:var(--danger); }
</style></head>
<body>
  <div id="sidebar">
    <div class="topo">
      <div class="marca">
        <div class="foto"><span class="ini">A</span><img id="avatar" src="/avatar" alt="" onerror="this.remove()"></div>
        <div><div class="nome">Alice</div><span class="suits"><span class="h">♥</span> ♠ <span class="h">♦</span> ♣</span></div>
      </div>
      <button id="novaConversa">✧ nova conversa</button>
    </div>
    <div id="convs"></div>
  </div>

  <div id="main">
    <header>
      <span class="titulo">Alice</span><span style="color:var(--gold);font-size:1.1rem">🫖</span>
      <span class="dim" id="modelo"></span>
      <div id="statusPill" class="pill ociosa" title="clique pra ver o histórico de atividade">
        <span class="ponto"></span><span id="statusTxt">ociosa</span>
      </div>
      <div class="grupo">
        <span class="dim">temp</span>
        <input type="range" id="temp" min="0.1" max="1.2" step="0.05">
        <span class="dim" id="tempval" style="width:2.4em"></span>
      </div>
      <div class="grupo" style="margin-left:auto">
        <button class="btn" id="btnMem">🧠 memória</button>
        <button class="btn" id="btnCfg">⚙ configurar</button>
      </div>
    </header>

    <div id="ativPanel"></div>
    <div id="log"></div>

    <footer>
      <textarea id="entrada" rows="1" placeholder="fala com a Alice…  (Enter envia, Shift+Enter quebra linha)"></textarea>
      <button id="enviar">enviar</button>
    </footer>
  </div>

  <!-- modal configuração -->
  <div class="overlay" id="ovCfg"><div class="modal">
    <h2>⚙ Configuração</h2>
    <div class="campo"><label>Modelo (Ollama)</label><input type="text" id="c_model"></div>
    <div class="campo"><label>Temperatura</label><input type="number" id="c_temp" step="0.05" min="0" max="2"></div>
    <div class="campo"><label>Contexto (num_ctx)</label><input type="number" id="c_ctx" step="1024" min="2048"></div>
    <div class="campo"><label>Ollama host</label><input type="text" id="c_host"></div>
    <div class="campo"><label>Projeto atual (workdir)</label><input type="text" id="c_wd" spellcheck="false"></div>
    <div class="campo"><label>Binário do Godot (godot_bin)</label><input type="text" id="c_godot" spellcheck="false"></div>
    <div class="campo"><label>Pasta de referência (só leitura — pra reproduzir um projeto)</label><input type="text" id="c_ref" spellcheck="false"></div>
    <div class="rodape">
      <button class="btn" onclick="fecha('ovCfg')">cancelar</button>
      <button class="btn" id="salvarCfg" style="background:var(--accent);color:#1a1024;border:none">salvar</button>
    </div>
  </div></div>

  <!-- modal memória -->
  <div class="overlay" id="ovMem"><div class="modal">
    <h2>🧠 Memória de longo prazo</h2>
    <p class="dim" style="margin-top:-8px;font-size:.82rem">Fatos que a Alice sempre lembra, em toda conversa.</p>
    <div id="fatos"></div>
    <div class="campo" style="margin-top:16px">
      <label>Adicionar fato</label>
      <input type="text" id="m_txt" placeholder="ex: o Ramon usa sempre Godot 4.7, nunca 3">
    </div>
    <div class="campo linha">
      <input type="text" id="m_tag" placeholder="tag (ex: godot)" style="max-width:160px">
      <button class="btn" id="addFato" style="background:var(--accent);color:#1a1024;border:none">adicionar</button>
    </div>
    <div class="rodape"><button class="btn" onclick="fecha('ovMem')">fechar</button></div>
  </div></div>

<script>
const $ = id => document.getElementById(id);
const log=$('log'), entrada=$('entrada'), btnEnviar=$('enviar'), temp=$('temp'), tempval=$('tempval');
let es=null, estado={};

function abre(id){ $(id).classList.add('on'); } function fecha(id){ $(id).classList.remove('on'); }

function rowMsg(cls, autor, texto){
  const row=document.createElement('div'); row.className='row '+cls;
  if(autor){ const a=document.createElement('div'); a.className='autor'; a.textContent=autor; row.appendChild(a); }
  const m=document.createElement('div'); m.className='msg'; m.textContent=texto||''; row.appendChild(m);
  log.appendChild(row); log.scrollTop=log.scrollHeight; return m;
}
function chip(txt){ const c=document.createElement('div'); c.className='tool'; c.textContent='⚙ '+txt;
  log.appendChild(c); log.scrollTop=log.scrollHeight; }
function mostrarImg(url){ const w=document.createElement('div'); w.className='shot';
  const cap=document.createElement('div'); cap.className='cap'; cap.textContent='📸 o jogo rodando:';
  const img=document.createElement('img'); img.src=url; img.onload=()=>log.scrollTop=log.scrollHeight;
  w.appendChild(cap); w.appendChild(img); log.appendChild(w); log.scrollTop=log.scrollHeight; }

async function carregarEstado(){
  estado = await (await fetch('/state')).json();
  $('modelo').textContent = estado.model;
  temp.value=estado.temperature; tempval.textContent=(+estado.temperature).toFixed(2);
}
async function carregarConversas(){
  const lista = await (await fetch('/conversas')).json();
  const box=$('convs'); box.innerHTML='';
  for(const c of lista){
    const d=document.createElement('div'); d.className='conv'+(c.id===estado.conv_atual?' ativa':'');
    d.innerHTML='<span class="x">✕</span><div class="t"></div><div class="d"></div>';
    d.querySelector('.t').textContent=c.titulo; d.querySelector('.d').textContent=c.atualizado;
    d.onclick=e=>{ if(e.target.classList.contains('x')) return; abrirConversa(c.id); };
    d.querySelector('.x').onclick=async e=>{ e.stopPropagation();
      await post('/apagar',{id:c.id}); if(c.id===estado.conv_atual){ await novaConversa(); } else { carregarConversas(); } };
    box.appendChild(d);
  }
}
async function abrirConversa(id){
  const d = await (await fetch('/conversa?id='+encodeURIComponent(id))).json();
  estado.conv_atual=id; log.innerHTML='';
  for(const m of d.messages){
    if(m.role==='user') rowMsg('u','você',m.content);
    else if(m.role==='assistant' && m.content) rowMsg('a','alice',m.content);
    else if(m.role==='tool') chip((m.tool_name||'tool'));
  }
  carregarConversas();
}
async function novaConversa(){ const r=await post('/nova',{}); estado.conv_atual=r.id; log.innerHTML=''; carregarConversas(); }

function post(url,obj){ return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(obj)}).then(r=>r.json()); }

temp.addEventListener('input',()=> tempval.textContent=(+temp.value).toFixed(2));
temp.addEventListener('change',()=> post('/config',{temperature:+temp.value}).then(carregarEstado));

$('novaConversa').onclick=novaConversa;
entrada.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); enviar(); }});
entrada.addEventListener('input',()=>{ entrada.style.height='auto'; entrada.style.height=entrada.scrollHeight+'px'; });
btnEnviar.onclick=enviar;

function enviar(){
  const msg=entrada.value.trim(); if(!msg||btnEnviar.disabled) return;
  rowMsg('u','você',msg); entrada.value=''; entrada.style.height='auto';
  btnEnviar.disabled=true; entrada.disabled=true;
  let alvo=null;
  es=new EventSource('/chat?msg='+encodeURIComponent(msg));
  es.onmessage=ev=>{ const d=JSON.parse(ev.data);
    if(d.type==='text'){ if(!alvo){ alvo=rowMsg('a','alice',''); alvo.classList.add('piscando'); }
      alvo.textContent+=d.data; log.scrollTop=log.scrollHeight; }
    else if(d.type==='tool'){ if(alvo) alvo.classList.remove('piscando'); chip(d.data); alvo=null; }
    else if(d.type==='image'){ mostrarImg(d.data); alvo=null; }
    else if(d.type==='error'){ chip('erro: '+d.data); }
    else if(d.type==='done'){ if(alvo) alvo.classList.remove('piscando');
      es.close(); btnEnviar.disabled=false; entrada.disabled=false; entrada.focus(); carregarConversas(); }
  };
  es.onerror=()=>{ if(es) es.close(); btnEnviar.disabled=false; entrada.disabled=false; };
}

/* ---- config ---- */
$('btnCfg').onclick=()=>{ $('c_model').value=estado.model; $('c_temp').value=estado.temperature;
  $('c_ctx').value=estado.num_ctx; $('c_host').value=estado.ollama_host;
  $('c_wd').value=estado.workdir; $('c_godot').value=estado.godot_bin;
  $('c_ref').value=estado.pasta_referencia||''; abre('ovCfg'); };
$('salvarCfg').onclick=async()=>{
  await post('/config',{ model:$('c_model').value.trim(), temperature:+$('c_temp').value,
    num_ctx:+$('c_ctx').value, ollama_host:$('c_host').value.trim(),
    workdir:$('c_wd').value.trim(), godot_bin:$('c_godot').value.trim(),
    pasta_referencia:$('c_ref').value.trim() });
  await carregarEstado(); fecha('ovCfg');
};

/* ---- memória ---- */
$('btnMem').onclick=async()=>{ await pintarMemoria(); abre('ovMem'); };
async function pintarMemoria(){
  const fatos=await (await fetch('/memoria')).json(); const box=$('fatos'); box.innerHTML='';
  if(!fatos.length){ box.innerHTML='<p class="dim" style="font-size:.85rem">(vazio — ela ainda não aprendeu nada permanente)</p>'; }
  fatos.forEach((f,i)=>{ const d=document.createElement('div'); d.className='fato';
    d.innerHTML='<div class="txt"><div class="tag"></div><div class="c"></div></div><span class="del">🗑</span>';
    d.querySelector('.tag').textContent=f.tag||'geral'; d.querySelector('.c').textContent=f.texto;
    d.querySelector('.del').onclick=async()=>{ await post('/memoria_del',{indice:i}); pintarMemoria(); };
    box.appendChild(d); });
}
$('addFato').onclick=async()=>{ const t=$('m_txt').value.trim(); if(!t) return;
  await post('/memoria_add',{texto:t,tag:$('m_tag').value.trim()||'geral'});
  $('m_txt').value=''; $('m_tag').value=''; pintarMemoria(); };

/* ---- monitor de atividade: você sempre vê se ela está trabalhando ---- */
const statusPill=$('statusPill'), statusTxt=$('statusTxt'), ativPanel=$('ativPanel');
const rotulos={ociosa:'ociosa', pensando:'pensando…', escrevendo:'escrevendo…', ferramenta:'trabalhando'};
statusPill.onclick=()=> ativPanel.classList.toggle('aberto');
async function poll(){
  try{
    const a=await (await fetch('/atividade')).json();
    const ativa = a.status!=='ociosa';
    statusPill.className='pill '+(ativa?'ativa':'ociosa');
    let txt = rotulos[a.status]||a.status;
    if(a.status==='ferramenta' && a.detalhe) txt='⚙ '+a.detalhe;
    if(ativa){ txt+=' · '+a.ha_seg+'s'; if(a.origem) txt+=' ('+a.origem+')'; }
    statusTxt.textContent=txt;
    ativPanel.innerHTML = (a.log||[]).map(e=>
      `<div class="ev">${e.t} <b>${e.status}</b> ${(e.detalhe||'')} ${e.origem?'· '+e.origem:''}</div>`
    ).join('') || '<div class="ev">(sem atividade ainda)</div>';
  }catch(e){ statusPill.className='pill ociosa'; statusTxt.textContent='servidor off?'; }
}
setInterval(poll, 1200); poll();

(async()=>{ await carregarEstado(); await carregarConversas(); entrada.focus(); })();
</script>
</body></html>
"""


# ------------------------------------------------------------------ servidor
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path == "/":
            corpo = PAGINA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif u.path == "/state":
            self._json(_estado())
        elif u.path == "/conversas":
            self._json(memory.listar_conversas())
        elif u.path == "/conversa":
            d = memory.carregar_conversa((q.get("id") or [""])[0])
            self._json(d or {"messages": []})
        elif u.path == "/memoria":
            self._json(longmemory.carregar())
        elif u.path == "/atividade":
            self._json({
                "status": _atividade["status"], "detalhe": _atividade["detalhe"],
                "origem": _atividade["origem"],
                "ha_seg": int(time.time() - _atividade["desde"]),
                "log": list(_ativ_log)[:12],
            })
        elif u.path == "/screenshot":
            self._servir_screenshot()
        elif u.path == "/avatar":
            self._servir_arquivo(AVATAR_PATH, "image/png")
        elif u.path == "/chat":
            self._chat((q.get("msg") or [""])[0])
        else:
            self.send_response(404); self.end_headers()

    def _servir_screenshot(self):
        self._servir_arquivo(str(tools.ULTIMO_SCREENSHOT), "image/png")

    def _servir_arquivo(self, caminho: str, tipo: str):
        if not os.path.isfile(caminho):
            self.send_response(404); self.end_headers(); return
        with open(caminho, "rb") as f:
            dados = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        u = urlparse(self.path)
        b = self._body()
        global conv_atual

        if u.path == "/config":
            _salvar_config(b)
            self._json({"ok": True, **_estado()})
        elif u.path == "/nova":
            with _lock:
                alice.reset()
                conv_atual = memory.novo_id()
            self._json({"ok": True, "id": conv_atual})
        elif u.path == "/apagar":
            memory.apagar_conversa(b.get("id", ""))
            self._json({"ok": True})
        elif u.path == "/memoria_add":
            longmemory.adicionar(b.get("texto", ""), b.get("tag", "geral"))
            _reconstruir_prompt()
            self._json({"ok": True})
        elif u.path == "/memoria_del":
            longmemory.remover(int(b.get("indice", -1)))
            _reconstruir_prompt()
            self._json({"ok": True})
        elif u.path == "/ask":
            self._ask(b)
        else:
            self.send_response(404); self.end_headers()

    def _ask(self, b: dict):
        """Endpoint simples request/response — usado pelo plugin do Godot.
        Recebe {msg, contexto} e devolve {resposta, ferramentas:[...]}."""
        msg = (b.get("msg") or "").strip()
        contexto = (b.get("contexto") or "").strip()
        if not msg:
            self._json({"resposta": "(mensagem vazia)", "ferramentas": []}); return
        full = f"[Contexto do editor Godot — {contexto}]\n\n{msg}" if contexto else msg
        partes, ferramentas = [], []
        with _lock:
            _atv("pensando", msg[:60], origem="editor (dock)")
            try:
                for kind, dado in alice.stream(full):
                    if kind == "text":
                        partes.append(dado)
                        _atv("escrevendo", origem="editor (dock)")
                    elif kind == "tool":
                        ferramentas.append(dado[0])
                        _atv("ferramenta", _resumo_tool(dado), origem="editor (dock)")
                _salvar_conversa_atual()
            except Exception as e:
                _atv("ociosa")
                self._json({"resposta": f"erro: {e}", "ferramentas": ferramentas}); return
            _atv("ociosa")
        self._json({"resposta": "".join(partes).strip(), "ferramentas": ferramentas})

    # ---------------------------------------------------------------- chat SSE
    def _chat(self, msg):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        if not msg.strip():
            emit({"type": "done"}); return
        with _lock:
            _atv("pensando", msg[:60], origem="interface web")
            try:
                tirou_shot = False
                for kind, dado in alice.stream(msg):
                    if kind == "text":
                        emit({"type": "text", "data": dado})
                        _atv("escrevendo", origem="interface web")
                    elif kind == "tool":
                        nome, args = dado
                        resumo = ", ".join(f"{k}={str(v)[:60]}" for k, v in (args or {}).items())
                        emit({"type": "tool", "data": f"{nome}({resumo})"})
                        _atv("ferramenta", _resumo_tool(dado), origem="interface web")
                        if nome == "godot_screenshot":
                            tirou_shot = True
                # se ela renderizou um screenshot, manda a imagem pra UI exibir
                if tirou_shot and tools.ULTIMO_SCREENSHOT.is_file():
                    mt = int(tools.ULTIMO_SCREENSHOT.stat().st_mtime)
                    emit({"type": "image", "data": f"/screenshot?t={mt}"})
                _salvar_conversa_atual()
                _atv("ociosa")
                emit({"type": "done"})
            except BrokenPipeError:
                _atv("ociosa")
            except Exception as e:
                _atv("ociosa")
                try:
                    emit({"type": "error", "data": str(e)}); emit({"type": "done"})
                except Exception:
                    pass


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 7861
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    url = f"http://127.0.0.1:{porta}"
    print(f"🤖 Alice web → {url}   | modelo: {cfg.model}  temp: {cfg.temperature}")
    print(f"   projeto: {os.path.abspath(cfg.workdir)}")
    print(f"   conversas: {len(memory.listar_conversas())}  | memória: {len(longmemory.carregar())} fatos")
    print("   (Ctrl+C pra desligar)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\naté mais! 👋")
        servidor.shutdown()


if __name__ == "__main__":
    main()
