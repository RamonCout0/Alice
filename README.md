# Alice 3 — companheira de Discord (Ollama local)

Remake completo: a Alice agora vive **inteira no Discord**. Conversa, pesquisa na web,
mestra Tormenta 20, gera imagem e pixel art, fala e toca música na call, avisa as
novidades do Gatuno de Estrelas e roda o Argos — tudo local, no seu PC.

```
Discord ──► alice/bot.py ──► alice/cerebro.py ──► Ollama (qwen3:8b ou o que você puser)
                                  │
              segurança ◄─────────┼─────────► memória em JSON (dados/)
                                  ▼
        ferramentas: web · t20 · rpg · imagem · pixelart · gatuno · argos · notas
```

## O que ela faz

| Área | Como usar |
|---|---|
| **Conversa** | marque, responda a ela, mande DM ou escreva "alice" na mensagem |
| **Pesquisa (DuckDuckGo)** | automático: em modelo pequeno (≤ 9B) ela é instruída a pesquisar fatos em vez de chutar |
| **Mestra de T20** | `/campanha criar` · `/sessao criar` · `/campanha mestra ativa:True` (ela narra o canal) · `/rolar` `/clima` `/terreno` `/viagem` `/recompensa` `/regra` |
| **Imagens** | `/imagem` ou "alice, desenha…" — ComfyUI + SDXL |
| **Pixel art que aprende** | `/pixelart` (aceita imagem para converter) · reaja 👍/👎 · `/pixelart_status` · `/pixelart_licao` |
| **Call: ouve e fala** | `/call entrar` — diga "Alice, …" na call e ela responde falando · `/call ouvir` · `/falar` |
| **Música** | `/tocar` `/pular` `/parar` `/fila` `/volume` (a música abaixa quando ela fala) |
| **Gatuno de Estrelas** | avisos automáticos no canal configurado · `/gatuno` · `/ideia` |
| **Argos** | `/argos projeto:<apelido>` (só o dono) |
| **Memória** | ela guarda fatos sobre cada pessoa · `/memoria` · `/esquecer` |

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen3:8b
copy config\alice.example.json config\alice.json
```

Edite `config/alice.json`: `dono_id` (seu ID do Discord), `servidor_id` (opcional, faz os
/comandos aparecerem na hora) e `canal_novidades_id` (onde avisar do Gatuno). O token vai
numa variável de ambiente, não no arquivo:

```bash
set DISCORD_TOKEN=seu_token
python -m alice
```

No portal do Discord, ligue o **Message Content Intent** e convide o bot com os escopos
`bot` + `applications.commands` (permissões: enviar mensagens, anexar arquivos, adicionar
reações, conectar e falar em voz).

### Extras opcionais

- **Imagens** — instale o [ComfyUI](https://github.com/comfyanonymous/ComfyUI) e deixe-o
  aberto (`http://127.0.0.1:8188`). Ponha em `models/checkpoints` um SDXL de anime
  (família Illustrious/NoobAI) e um realista (Juggernaut XL), e em `models/loras` um LoRA
  de pixel art para SDXL. Os nomes dos arquivos vão em `comfy_modelos` / `comfy_lora_pixel`.
  Numa RTX 5060 Ti, SDXL 1024px sai em poucos segundos; `liberar_vram` descarrega o LLM
  antes de gerar para os dois não disputarem a placa.
- **Voz e música** — `winget install Gyan.FFmpeg`. Três motores em `voz.motor`:
  - `edge` (padrão): edge-tts pt-BR com tom agudo e filtro sintético, estilo vocaloid.
    É a única que fala palavras de verdade.
  - `chipforge`: a fala é montada som por som. O texto vira fonemas pelas regras do
    português; as vogais saem da cantora por formantes do
    [ChipForge](https://github.com/RamonCout0/chipforge) e as consoantes são sintetizadas
    (chiado para s/f/x, estalo para p/t/k, boca fechada para m/n). É síntese por regra:
    sai robótica, com cara de vocaloid. Clone o ChipForge, `pip install scipy` e aponte
    `voz.chipforge_dir` para a pasta.
  - `externo`: qualquer sintetizador por linha de comando (OpenUtau, Piper…) em
    `voz.comando_externo`, com `{texto}` e `{saida}` (um .wav).
  `pasta_musicas` aponta para trilhas locais (ex.: a pasta `musicas/` do rpg-song);
  `/tocar musica:<nome> repetir:True` deixa uma trilha ambiente em loop.
- **Ouvir a call** — `pip install discord-ext-voice-recv faster-whisper`. Com isso, ao
  entrar na call (`/call entrar`) ela transcreve o que cada pessoa fala com o Whisper
  rodando no seu PC e responde quando dizem "Alice" (ou nos 25 s seguintes a uma resposta
  dela, para a conversa fluir). A fala passa pelas mesmas travas de segurança do texto, com
  o nível de quem falou. O áudio não é gravado. Ajustes em `escuta` no config (`modelo`:
  `small` é um bom ponto de partida na GPU; `precisa_chamar`; `ativa`). `/call ouvir` liga
  e desliga na hora.
- **Livros de regra** — `python -m alice.indexar_livro "C:\...\Tormenta20.pdf" t20` cria um
  índice local para `/regra` e para a ferramenta `consultar_regra`.
- **Argos** — `argos_dir` (pasta do Argos) e `argos_projetos` (`{"apelido": "C:/pasta"}`).

## Segurança (prompt injection)

Nenhuma trava depende de o modelo "obedecer" — modelo de 8B cai em jailbreak, então as
regras ficam no código (`alice/seguranca.py`):

1. **Permissão por código.** Níveis dono / confiável / membro / bloqueado. O modelo só
   recebe as ferramentas que o nível de quem falou permite, e a checagem é refeita ao
   executar. Dizer "sou o dono" não muda nada: o nível vem do ID do Discord.
2. **Entrada higienizada.** Caracteres invisíveis, `system:` falso, `<|im_start|>` e nome
   de exibição malicioso são neutralizados antes de chegar ao modelo.
3. **Detector de injeção.** Mensagem com cara de ataque é respondida **sem ferramentas**;
   três tentativas em 15 min = 10 min de castigo.
4. **Dados externos rotulados.** Web, memória e livros entram em blocos `<<DADOS>>`, com
   linhas de instrução embutida removidas.
5. **Saída filtrada.** Token, canário do prompt e `@everyone` nunca saem.
6. **Memória à prova de plantio.** Fato só é gravado no perfil de quem falou, e fato com
   cara de instrução é recusado.
7. **Sem shell.** Argos e voz externa rodam com lista de argumentos; o Argos só aceita
   apelidos do config; `abrir_pagina` bloqueia endereços internos (SSRF).

Não é à prova de tudo — é defesa em camadas. O que um ataque bem-sucedido consegue é, no
máximo, fazê-la falar bobagem: não há ferramenta de arquivo nem de comando no Discord.

## Estrutura

```
alice/
  bot.py            Discord: mensagens, /comandos, reações, call, loop do Gatuno
  cerebro.py        fluxo de uma mensagem (segurança → memória → LLM → filtro)
  llm.py            cliente do Ollama + loop de ferramentas
  seguranca.py      tudo de prompt injection e limites
  memoria.py        perfis e histórico em JSON
  voz.py            mixer de áudio, fala e música
  voz_chipforge.py  fala montada fonema a fonema com a cantora do ChipForge
  ouvido.py         escuta da call: áudio → frases → texto (Whisper local)
  ferramentas/      web, t20 (+ regras do artoniana), rpg, imagem, pixelart, gatuno, argos, notas
config/             alice.example.json, persona.md
dados/              criado em runtime (memória, campanhas, aprendizado) — fora do git
tests/              pytest (53 testes)
```

Testes: `python -m pytest tests -q`

## Navi (Códice) — ainda não ligado

A ideia é a Alice ser a primeira GM ativa do mundo dos NAVIs do Projeto Códice. Como o
Códice ainda não tem servidor nem protocolo para isso, nada foi implementado. O que já
serve de base quando existir: o modo mestra (`/campanha mestra`), o estado de campanha em
`dados/rpg/` e o registro de ferramentas — uma integração nova é um arquivo em
`alice/ferramentas/` com funções `@ferramenta`.

## Histórico

A Alice 2.0 (assistente de código para Godot: `core/`, `frontends/`, `conhecimento/`…)
foi removida neste remake. Continua no histórico do git, até o commit `3ce887f`.
