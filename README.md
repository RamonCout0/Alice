# 🤖 Alice 2.0 — Assistente de código pessoal (Ollama + agente + MCP)

Evolução da Alice: um **núcleo (cérebro) único** compartilhado por vários frontends.
Agora ela não só conversa — ela **lê seu código, roda comandos e usa ferramentas**
de verdade, rodando 100% local no seu PC via [Ollama](https://ollama.com).

```
                 ┌──────────────┐
   Web (navegador)│             │  read_file / write_file / run_command …
   CLI (terminal) │   core/     │  godot: check_syntax / rodar / screenshot
   Discord        │   Agent     │  conhecimento: buscar_padrao / godot_doc /
   Plugin Godot   │  (tool loop)│    buscar_doc / diagnosticar_erro
                 └──────┬───────┘  + ferramentas MCP (git, filesystem…)
                        │
                   Ollama local (qwen3:8b)
```

## 🧩 Como ela programa Godot sem errar (método quebra-cabeça)

Modelo pequeno não inventa código — ele **monta** com peças confiáveis:

1. **`conhecimento/godot_4.json`** — biblioteca de padrões (blocos Lego) validados;
   ela busca um esqueleto pronto e adapta.
2. **`conhecimento/godot_api/`** — a documentação **oficial completa** do Godot 4.7
   (1071 classes, gerada da tag `4.7-stable`): assinatura exata de todo método,
   propriedade, sinal e constante. Ferramentas `godot_doc` e `buscar_doc`.
3. **`conhecimento/godot_erros.json`** — dicionário de erros comuns (Godot 3→4,
   GDScript, runtime). `check_godot_syntax` e `godot_rodar` anexam o diagnóstico
   (causa + correção) automaticamente quando reconhecem o erro.
4. Validação real: `check_godot_syntax` → `godot_rodar` → `godot_screenshot`,
   e o que ela aprende e valida vira padrão novo com `salvar_padrao`.

## 📁 Estrutura

```
Alice/
├── core/
│   ├── config.py     # carrega config + personalidade, monta o system prompt
│   ├── tools.py      # as "mãos": arquivos, shell, godot, conhecimento
│   ├── agent.py      # o "cérebro": loop de tool-calling com Ollama (streaming)
│   ├── docs.py       # consulta à documentação oficial do Godot 4.7 embutida
│   ├── biblioteca.py # biblioteca de padrões (blocos Lego) de GDScript
│   ├── memory.py     # conversas persistentes
│   └── longmemory.py # memória de longo prazo (fatos permanentes)
├── conhecimento/
│   ├── godot_api/    # documentação oficial 4.7 completa em JSON (1071 classes)
│   ├── godot_4.json  # padrões validados (crescem com o tempo)
│   └── godot_erros.json # erros comuns → causa + correção
├── mcp_bridge/
│   └── bridge.py     # conecta servidores MCP reais ao loop do Ollama
├── frontends/
│   ├── web/          # interface web (Tailwind local, markdown, código destacado)
│   ├── webui.py      # servidor da interface web (stdlib pura)
│   ├── cli.py        # Alice no terminal
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

**Interface web (a principal):**
```bash
python -m frontends.webui        # abre http://127.0.0.1:7861
```

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
