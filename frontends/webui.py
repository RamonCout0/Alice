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
cfg = load_config()
tools.configure(workdir=cfg.workdir, confirm_cb=None, godot_bin=cfg.godot_bin)
alice = Agent(cfg, build_system_prompt(cfg))
conv_atual = memory.novo_id()          # id da conversa em andamento
_lock = threading.Lock()               # uma geração por vez


# ---- helpers de estado --------------------------------------------------
def _estado() -> dict:
    return {
        "model": cfg.model, "temperature": cfg.temperature, "num_ctx": cfg.num_ctx,
        "ollama_host": cfg.ollama_host, "workdir": os.path.abspath(cfg.workdir),
        "godot_bin": cfg.godot_bin, "conv_atual": conv_atual,
    }


def _reconstruir_prompt():
    """Atualiza o system prompt (projeto/memória) preservando o histórico."""
    alice.messages[0] = {"role": "system", "content": build_system_prompt(cfg)}


def _salvar_config(mudancas: dict):
    campos = {"model", "temperature", "num_ctx", "ollama_host", "workdir",
              "godot_bin", "confirm_commands"}
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
    tools.configure(workdir=cfg.workdir, confirm_cb=None, godot_bin=cfg.godot_bin)
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
  :root{ --bg:#0e1016; --panel:#161923; --panel2:#1e2230; --panel3:#252a3a; --txt:#e6e8ee;
         --dim:#8b90a0; --accent:#c084fc; --accent2:#a855f7; --user:#2a3350; --tool:#1c2e2a;
         --line:#272c3a; --danger:#ef6b6b; }
  *{ box-sizing:border-box; }
  html,body{ margin:0; height:100%; }
  body{ display:flex; font-family:system-ui,Segoe UI,Roboto,sans-serif; background:var(--bg);
        color:var(--txt); height:100vh; overflow:hidden; }

  /* -------- sidebar -------- */
  #sidebar{ width:250px; background:var(--panel); border-right:1px solid var(--line);
            display:flex; flex-direction:column; flex-shrink:0; }
  #sidebar .topo{ padding:14px; border-bottom:1px solid var(--line); }
  #novaConversa{ width:100%; background:var(--accent); color:#1a1024; border:none; border-radius:9px;
                 padding:10px; font-weight:600; cursor:pointer; font-size:.9rem; }
  #convs{ flex:1; overflow-y:auto; padding:8px; }
  .conv{ padding:9px 10px; border-radius:8px; cursor:pointer; margin-bottom:4px; font-size:.86rem;
         display:flex; flex-direction:column; gap:2px; }
  .conv:hover{ background:var(--panel2); }
  .conv.ativa{ background:var(--panel3); }
  .conv .t{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .conv .d{ font-size:.7rem; color:var(--dim); }
  .conv .x{ float:right; color:var(--dim); font-size:.9rem; opacity:0; }
  .conv:hover .x{ opacity:1; }
  .conv .x:hover{ color:var(--danger); }

  /* -------- área principal -------- */
  #main{ flex:1; display:flex; flex-direction:column; min-width:0; }
  header{ display:flex; align-items:center; gap:14px; padding:10px 16px; background:var(--panel);
          border-bottom:1px solid var(--line); flex-wrap:wrap; }
  header .titulo{ font-weight:600; font-size:1.05rem; }
  header .dim{ color:var(--dim); font-size:.8rem; }
  header .grupo{ display:flex; align-items:center; gap:8px; }
  header input[type=range]{ accent-color:var(--accent); }
  .btn{ background:var(--panel2); color:var(--txt); border:1px solid var(--line);
        border-radius:8px; padding:7px 12px; font-size:.82rem; cursor:pointer; }
  .btn:hover{ border-color:var(--accent); }

  #log{ flex:1; overflow-y:auto; padding:22px; display:flex; flex-direction:column; gap:14px; }
  .row{ display:flex; flex-direction:column; }
  .row.u{ align-items:flex-end; } .row.a{ align-items:flex-start; }
  .msg{ max-width:82%; padding:11px 14px; border-radius:12px; white-space:pre-wrap;
        word-wrap:break-word; line-height:1.5; font-size:.95rem; }
  .u .msg{ background:var(--user); border-bottom-right-radius:3px; }
  .a .msg{ background:var(--panel2); border-bottom-left-radius:3px; }
  .tool{ align-self:flex-start; background:var(--tool); color:#9fdcc0; font-family:ui-monospace,monospace;
         font-size:.78rem; padding:6px 10px; border-radius:8px; max-width:82%; }
  .autor{ font-size:.72rem; color:var(--dim); margin:0 6px 4px; }
  .shot{ align-self:flex-start; max-width:82%; }
  .shot .cap{ font-size:.72rem; color:var(--dim); margin:0 4px 5px; }
  .shot img{ max-width:100%; border-radius:10px; border:1px solid var(--line); display:block; }
  footer{ display:flex; gap:10px; padding:14px 16px; background:var(--panel); border-top:1px solid var(--line); }
  #entrada{ flex:1; resize:none; background:var(--panel2); color:var(--txt); border:1px solid var(--line);
            border-radius:10px; padding:11px 13px; font-size:.95rem; font-family:inherit; max-height:170px; }
  #enviar{ background:var(--accent); color:#1a1024; border:none; border-radius:10px; padding:0 22px;
           font-weight:600; cursor:pointer; font-size:.95rem; }
  #enviar:disabled{ opacity:.5; cursor:default; }
  .piscando::after{ content:"▋"; animation:blink 1s steps(2) infinite; color:var(--accent); }
  @keyframes blink{ 50%{ opacity:0; } }

  /* -------- modais -------- */
  .overlay{ position:fixed; inset:0; background:rgba(0,0,0,.55); display:none;
            align-items:center; justify-content:center; z-index:10; }
  .overlay.on{ display:flex; }
  .modal{ background:var(--panel); border:1px solid var(--line); border-radius:14px; width:min(560px,92vw);
          max-height:86vh; overflow-y:auto; padding:22px; }
  .modal h2{ margin:0 0 16px; font-size:1.15rem; }
  .campo{ margin-bottom:14px; }
  .campo label{ display:block; font-size:.8rem; color:var(--dim); margin-bottom:5px; }
  .campo input[type=text], .campo input[type=number]{ width:100%; background:var(--panel2); color:var(--txt);
          border:1px solid var(--line); border-radius:8px; padding:9px 11px; font-size:.9rem; }
  .campo.linha{ display:flex; align-items:center; gap:8px; }
  .modal .rodape{ display:flex; justify-content:flex-end; gap:10px; margin-top:8px; }
  .fato{ background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:9px 11px;
         margin-bottom:8px; display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
  .fato .tag{ font-size:.68rem; color:var(--accent); text-transform:uppercase; }
  .fato .txt{ font-size:.88rem; flex:1; }
  .fato .del{ color:var(--dim); cursor:pointer; } .fato .del:hover{ color:var(--danger); }
</style></head>
<body>
  <div id="sidebar">
    <div class="topo"><button id="novaConversa">+ nova conversa</button></div>
    <div id="convs"></div>
  </div>

  <div id="main">
    <header>
      <span class="titulo">🤖 Alice</span>
      <span class="dim" id="modelo"></span>
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
  $('c_wd').value=estado.workdir; $('c_godot').value=estado.godot_bin; abre('ovCfg'); };
$('salvarCfg').onclick=async()=>{
  await post('/config',{ model:$('c_model').value.trim(), temperature:+$('c_temp').value,
    num_ctx:+$('c_ctx').value, ollama_host:$('c_host').value.trim(),
    workdir:$('c_wd').value.trim(), godot_bin:$('c_godot').value.trim() });
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
        elif u.path == "/screenshot":
            self._servir_screenshot()
        elif u.path == "/chat":
            self._chat((q.get("msg") or [""])[0])
        else:
            self.send_response(404); self.end_headers()

    def _servir_screenshot(self):
        p = tools.ULTIMO_SCREENSHOT
        if not p.is_file():
            self.send_response(404); self.end_headers(); return
        dados = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
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
        else:
            self.send_response(404); self.end_headers()

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
            try:
                tirou_shot = False
                for kind, dado in alice.stream(msg):
                    if kind == "text":
                        emit({"type": "text", "data": dado})
                    elif kind == "tool":
                        nome, args = dado
                        resumo = ", ".join(f"{k}={str(v)[:60]}" for k, v in (args or {}).items())
                        emit({"type": "tool", "data": f"{nome}({resumo})"})
                        if nome == "godot_screenshot":
                            tirou_shot = True
                # se ela renderizou um screenshot, manda a imagem pra UI exibir
                if tirou_shot and tools.ULTIMO_SCREENSHOT.is_file():
                    mt = int(tools.ULTIMO_SCREENSHOT.stat().st_mtime)
                    emit({"type": "image", "data": f"/screenshot?t={mt}"})
                _salvar_conversa_atual()
                emit({"type": "done"})
            except BrokenPipeError:
                pass
            except Exception as e:
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
