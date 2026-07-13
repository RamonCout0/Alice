# 🤖 Alice 2.0 — Assistente de código pessoal (Ollama + agente + MCP)

Evolução da Alice: um **núcleo (cérebro) único** compartilhado por vários frontends.
Agora ela não só conversa — ela **lê seu código, roda comandos e usa ferramentas**
de verdade, rodando 100% local no seu PC via [Ollama](https://ollama.com).

```
                 ┌──────────────┐
   CLI (terminal)│              │  read_file / list_dir / search_code
   Discord       │   core/      │  write_file / run_command
   (futuro: web) │   Agent      │  + ferramentas MCP (git, filesystem, github…)
                 │  (tool loop) │
                 └──────┬───────┘
                        │
                   Ollama local (qwen2.5-coder:7b)
```

## 📁 Estrutura

```
Alice 2.0/
├── core/
│   ├── config.py     # carrega config + personalidade, monta o system prompt
│   ├── tools.py      # as "mãos": ler/escrever arquivo, buscar, rodar comando
│   ├── agent.py      # o "cérebro": loop de tool-calling com Ollama (streaming)
│   └── memory.py     # salvar/carregar sessões
├── mcp_bridge/
│   └── bridge.py     # conecta servidores MCP reais ao loop do Ollama
├── frontends/
│   ├── cli.py        # Alice no terminal (agente de código)
│   └── discord/bot.py# Alice no Discord (mesmo core)
├── config/
│   ├── config.example.json
│   └── personalidade.json
└── requirements.txt
```

## ⚙️ Setup

```bash
# 1. Dependências
pip install -r requirements.txt

# 2. Modelo de código (suporta tool-calling — essencial p/ o agente)
ollama pull qwen2.5-coder:7b

# 3. Configuração
cp config/config.example.json config/config.json
#   edite se quiser (modelo, workdir, discord_token, mcp_servers…)
```

## 🚀 Uso

**No terminal (dentro de qualquer projeto):**
```bash
python -m frontends.cli /caminho/do/seu/projeto
```
Aí é só pedir: *"analisa a estrutura desse projeto e me diz o que o main.py faz"* —
ela vai **ler os arquivos de verdade** antes de responder.

Comandos da CLI: `/reset` · `/cwd <pasta>` · `/salvar <nome>` · `/sair`

**No Discord:**
```bash
# coloque o discord_token no config.json
python -m frontends.discord.bot
```

## 🔌 MCP (ferramentas externas)

Edite `mcp_servers` no `config.json` e ponha `"disabled": false`. Exemplos já vêm
prontos (filesystem, git). Precisa de `npx` (Node) ou `uvx` (uv) instalado.
As ferramentas do servidor MCP entram automaticamente no mesmo loop da Alice.

## 🧩 Por que essa arquitetura

- **Prompt** (`personalidade.json`) define *quem* a Alice é.
- **Agent + tools** define *o que ela consegue fazer* — um prompt sozinho não lê arquivos.
- **Frontends** são finos: só recebem input e chamam o mesmo `Agent`.

Trocar de modelo, adicionar ferramenta ou criar um frontend novo (web, VS Code)
não exige mexer no cérebro.

## 🔒 Segurança

- `run_command` pede confirmação na CLI (`confirm_commands: true`).
- As ferramentas são **escopadas ao `workdir`** — a Alice não lê fora do projeto.
- Nunca suba `config/config.json` (tokens) — já está no `.gitignore`.
```
