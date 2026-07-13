# ============================================================
#  mcp_bridge/bridge.py — conecta servidores MCP reais ao loop do Ollama
#
#  MCP é assíncrono; o Agent é síncrono. Solução: rodamos um event loop
#  em uma thread de fundo e expomos chamadas síncronas.
#
#  Requer:  pip install mcp
#  Servidores MCP são configurados em config.json -> "mcp_servers".
# ============================================================
import asyncio
import os
import threading


class MCPManager:
    def __init__(self, servers: dict, workdir: str = "."):
        # ignora entradas de comentário/desabilitadas
        self.servers = {
            n: s for n, s in servers.items()
            if isinstance(s, dict) and not s.get("disabled") and s.get("command")
        }
        self.workdir = workdir
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self._sessions = {}     # server_name -> ClientSession
        self._tool_index = {}   # tool_name  -> server_name
        self.tool_specs = []    # specs no formato do Ollama
        self._stack = None

    # ---- infra do event loop em background --------------------------------
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    # ---- ciclo de vida -----------------------------------------------------
    def start(self):
        """Sobe os servidores e indexa as ferramentas. Retorna nº de tools."""
        if not self.servers:
            return 0
        self.thread.start()
        self._submit(self._connect_all())
        return len(self._tool_index)

    async def _connect_all(self):
        from contextlib import AsyncExitStack
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        for name, spec in self.servers.items():
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env"),
                cwd=self.workdir,
            )
            try:
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
            except Exception as e:
                print(f"[MCP] servidor '{name}' falhou ao iniciar, ignorando: {e}")
                continue
            self._sessions[name] = session

            for t in (await session.list_tools()).tools:
                self._tool_index[t.name] = name
                self.tool_specs.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    },
                })

    # ---- execução síncrona de uma ferramenta MCP --------------------------
    def call(self, name: str, args: dict) -> str:
        return self._submit(self._call(name, args))

    async def _call(self, name: str, args: dict) -> str:
        session = self._sessions[self._tool_index[name]]
        result = await session.call_tool(name, args or {})
        partes = [getattr(c, "text", str(c)) for c in result.content]
        return "\n".join(partes) or "(sem retorno)"

    def dispatch(self) -> dict:
        """{nome_da_tool: callable} para o Agent executar."""
        return {
            name: (lambda n: lambda **kw: self.call(n, kw))(name)
            for name in self._tool_index
        }


def carregar_mcp(cfg):
    """
    Tenta subir os servidores MCP. Falha graciosamente se o pacote `mcp`
    não estiver instalado ou não houver servidores ativos.
    Retorna (tool_specs, dispatch).
    """
    if not cfg.mcp_servers:
        return [], {}
    try:
        mgr = MCPManager(cfg.mcp_servers, workdir=os.path.abspath(cfg.workdir))
        n = mgr.start()
        if n == 0:
            return [], {}
        print(f"[MCP] {n} ferramentas carregadas de {len(mgr._sessions)} servidor(es).")
        return mgr.tool_specs, mgr.dispatch()
    except ImportError:
        print("[MCP] pacote 'mcp' não instalado — pulando. (pip install mcp)")
        return [], {}
    except Exception as e:
        print(f"[MCP] Falha ao iniciar servidores: {e}")
        return [], {}
