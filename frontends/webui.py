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


# ---------------------------------------------------------------- frontend
# A interface mora em frontends/web/ (index.html + app.js + alice.css +
# tailwind.js + fonts/) e é servida como arquivos estáticos daqui.
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

_MIMES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
          ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


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
            self._servir_estatico("index.html")
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
            self._servir_avatar()
        elif u.path == "/chat":
            self._chat((q.get("msg") or [""])[0])
        else:
            self._servir_estatico(u.path.lstrip("/"))

    def _servir_estatico(self, rel: str):
        """Serve um arquivo de frontends/web/ (index.html, app.js, fontes…)."""
        alvo = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not alvo.startswith(os.path.abspath(WEB_DIR)) or not os.path.isfile(alvo):
            self.send_response(404); self.end_headers(); return
        mime = _MIMES.get(os.path.splitext(alvo)[1], "application/octet-stream")
        self._servir_arquivo(alvo, mime)

    def _servir_screenshot(self):
        self._servir_arquivo(str(tools.ULTIMO_SCREENSHOT), "image/png")

    def _servir_avatar(self):
        import glob
        mimes = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "webp": "image/webp", "gif": "image/gif"}
        pasta = os.path.dirname(AVATAR_PATH)
        for ext, mime in mimes.items():
            achados = sorted(glob.glob(os.path.join(pasta, "alice*." + ext)))
            if achados:
                self._servir_arquivo(achados[0], mime)
                return
        self.send_response(404); self.end_headers()

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
