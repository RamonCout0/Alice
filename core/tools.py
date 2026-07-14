# ============================================================
#  core/tools.py — ferramentas locais da Alice (as "mãos")
#  Todas escopadas ao diretório do projeto (workdir) por segurança.
# ============================================================
import os
import re
import glob
import shutil
import tempfile
import pathlib
import subprocess

_WORKDIR: pathlib.Path = pathlib.Path(".").resolve()
# onde o último screenshot renderizado é guardado (a interface web exibe)
ULTIMO_SCREENSHOT = pathlib.Path(__file__).resolve().parent.parent / "ultimo_screenshot.png"
_CONFIRM = None  # callback(cmd: str) -> bool ; definido pelo frontend
_GODOT_BIN = ""  # caminho do binário do Godot ; definido pelo frontend via configure()

_IGNORAR = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", ".mypy_cache"}

# a própria pasta onde a Alice mora (raiz do projeto: pai de core/)
_ALICE_DIR = pathlib.Path(__file__).resolve().parent.parent


def _autoprotegido(p: pathlib.Path) -> bool:
    """True se `p` está dentro da própria instalação da Alice."""
    return p == _ALICE_DIR or _ALICE_DIR in p.parents


def _sem_confirmacao_real() -> bool:
    """
    True quando não existe um canal de confirmação humana de verdade (ex:
    Discord, onde 'confirmo' no chat não trava nada no código). Nesse caso a
    Alice nunca pode escrever/rodar comando na própria pasta de instalação —
    autoproteção contra ela se automodificar/autodestruir sem supervisão real.
    """
    return _CONFIRM is None


def configure(workdir: str = ".", confirm_cb=None, godot_bin: str = ""):
    """Define a raiz do projeto, o callback de confirmação e o binário do Godot."""
    global _WORKDIR, _CONFIRM, _GODOT_BIN
    _WORKDIR = pathlib.Path(workdir).resolve()
    _CONFIRM = confirm_cb
    _GODOT_BIN = godot_bin


def _safe(path: str) -> pathlib.Path:
    """Resolve o caminho e garante que ele fica DENTRO do workdir."""
    p = (_WORKDIR / path).resolve()
    if _WORKDIR != p and _WORKDIR not in p.parents:
        raise ValueError(f"Acesso negado fora do projeto: {path}")
    return p


# ------------------------------------------------------------------ ferramentas

def read_file(path: str) -> str:
    """Lê e retorna o conteúdo de um arquivo de texto do projeto."""
    p = _safe(path)
    if not p.is_file():
        return f"Arquivo não encontrado: {path}"
    return p.read_text(encoding="utf-8", errors="replace")[:20000]


def list_dir(path: str = ".") -> str:
    """Lista os arquivos e subpastas de um diretório do projeto."""
    p = _safe(path)
    if not p.is_dir():
        return f"Diretório não encontrado: {path}"
    itens = []
    for c in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if c.name in _IGNORAR or c.name.startswith("."):
            continue
        itens.append(c.name + ("/" if c.is_dir() else ""))
    return "\n".join(itens) or "(vazio)"


def write_file(path: str, content: str) -> str:
    """Cria ou sobrescreve um arquivo de texto no projeto com o conteúdo dado."""
    p = _safe(path)
    if _autoprotegido(p) and _sem_confirmacao_real():
        return "ERRO: autoproteção — sem confirmação real disponível aqui, não posso escrever na minha própria pasta de instalação."
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Arquivo salvo: {path} ({len(content)} caracteres)"


def search_code(pattern: str, path: str = ".") -> str:
    """Procura um texto ou regex nos arquivos do projeto (grep). Retorna arquivo:linha."""
    base = _safe(path)
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Regex inválida: {e}"
    hits = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _IGNORAR and not d.startswith(".")]
        for fn in files:
            fp = pathlib.Path(root) / fn
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        rel = fp.relative_to(_WORKDIR)
                        hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                        if len(hits) >= 40:
                            return "\n".join(hits) + "\n… (limitado a 40 resultados)"
            except Exception:
                continue
    return "\n".join(hits) or "Nenhuma ocorrência encontrada."


def run_command(command: str) -> str:
    """Executa um comando de shell no diretório do projeto e retorna a saída."""
    if _autoprotegido(_WORKDIR) and _sem_confirmacao_real():
        return "ERRO: autoproteção — sem confirmação real disponível aqui, não posso rodar comandos com a minha própria pasta de instalação como projeto."
    if _CONFIRM is not None and not _CONFIRM(command):
        return "Comando cancelado pelo usuário."
    try:
        r = subprocess.run(
            command, shell=True, cwd=str(_WORKDIR),
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Comando excedeu o tempo limite (120s)."
    saida = (r.stdout + r.stderr).strip()
    return saida[:10000] or f"(sem saída · código de retorno {r.returncode})"


def check_godot_syntax(path: str) -> str:
    """Valida a sintaxe de um script .gd do projeto rodando o Godot em modo headless (--check-only). Use depois de escrever qualquer script GDScript, antes de considerar terminado. LIMITAÇÃO CONHECIDA: --check-only não resolve autoloads/singletons do projeto, então um erro tipo 'Identifier not found: NomeDoAutoload' pode ser FALSO POSITIVO — confira o project.godot (seção [autoload]) antes de tentar 'corrigir' esse tipo de erro especificamente."""
    if not _GODOT_BIN:
        return "ERRO: nenhum binário do Godot configurado (godot_bin no config.json)."
    p = _safe(path)
    if not p.is_file():
        return f"Arquivo não encontrado: {path}"
    try:
        r = subprocess.run(
            [_GODOT_BIN, "--headless", "--script", str(p.relative_to(_WORKDIR)), "--check-only"],
            cwd=str(_WORKDIR), capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "Checagem excedeu o tempo limite (60s)."
    saida = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and "SCRIPT ERROR" not in saida and "ERROR" not in saida:
        return f"OK — {path} sem erros de sintaxe."
    return saida[:6000] or f"Falhou (código {r.returncode}), sem detalhes na saída."


def lembrar(fato: str, tag: str = "geral") -> str:
    """Guarda na MEMÓRIA DE LONGO PRAZO um fato que deve valer pra sempre, em
    qualquer conversa futura (preferência do Ramon, decisão de projeto, convenção
    de código, algo importante que você aprendeu). Use com parcimônia, só pra
    coisas realmente duradouras — NÃO pra detalhes efêmeros da conversa atual.
    'tag' é uma categoria curta (ex: 'godot', 'preferencia', 'projeto')."""
    from core import longmemory
    ok = longmemory.adicionar(fato, tag)
    return f"Guardado na memória de longo prazo: {fato}" if ok else "Isso eu já sabia (não dupliquei)."


def godot_project_info() -> str:
    """Resume o project.godot do projeto atual: versão do Godot (config/features),
    cena principal, autoloads/singletons e ações de input. Use isto ANTES de mexer
    num projeto Godot pra entender a estrutura e não quebrar convenções."""
    p = _WORKDIR / "project.godot"
    if not p.is_file():
        return "Não há project.godot na raiz do projeto atual (não é um projeto Godot?)."
    txt = p.read_text(encoding="utf-8", errors="replace")
    secao = None
    features, main_scene, autoloads, inputs = [], None, [], []
    for linha in txt.splitlines():
        s = linha.strip()
        if s.startswith("[") and s.endswith("]"):
            secao = s[1:-1]
            continue
        if not s or s.startswith(";") or "=" not in s:
            continue
        chave, _, valor = s.partition("=")
        chave, valor = chave.strip(), valor.strip()
        if chave == "config/features":
            features.append(valor.strip('"[] '))
        elif chave == "run/main_scene":
            main_scene = valor.strip('"')
        elif secao == "autoload":
            autoloads.append(f"{chave} = {valor}")
        elif secao == "input":
            inputs.append(chave)
    partes = ["📦 project.godot:"]
    partes.append(f"  versão/features: {', '.join(features) if features else '?'}")
    partes.append(f"  cena principal: {main_scene or '?'}")
    partes.append(f"  autoloads/singletons: {', '.join(a.split(' = ')[0] for a in autoloads) if autoloads else '(nenhum)'}")
    if autoloads:
        partes += [f"    {a}" for a in autoloads]
    partes.append(f"  ações de input: {', '.join(inputs) if inputs else '(nenhuma)'}")
    return "\n".join(partes)


def _erros_godot(saida: str) -> list[str]:
    """Extrai linhas de erro de runtime da saída do Godot."""
    return [l for l in saida.splitlines()
            if "SCRIPT ERROR" in l or l.strip().startswith("ERROR")
            or "Parse Error" in l or "Cannot" in l]


def godot_rodar(cena: str = "", frames: int = 180) -> str:
    """RODA o jogo/uma cena de verdade em modo headless por 'frames' quadros e
    reporta ERROS DE RUNTIME (não só de sintaxe — pega erros que só aparecem
    quando o jogo executa: null, sinais mal conectados, chamadas inválidas etc).
    Use depois de check_godot_syntax pra validar de verdade. 'cena' é o caminho
    de uma .tscn do projeto (ex: 'Player/player.tscn'); vazio = cena principal."""
    if not _GODOT_BIN:
        return "ERRO: nenhum binário do Godot configurado (godot_bin no config.json)."
    if not (_WORKDIR / "project.godot").is_file():
        return "ERRO: a pasta atual não é um projeto Godot (sem project.godot)."
    frames = max(1, min(int(frames), 3600))
    cmd = [_GODOT_BIN, "--headless", "--path", str(_WORKDIR), "--quit-after", str(frames)]
    if cena:
        cmd.append(cena)
    try:
        r = subprocess.run(cmd, cwd=str(_WORKDIR), capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return "Execução excedeu o tempo limite (90s) — pode estar em loop infinito."
    saida = (r.stdout + r.stderr).strip()
    erros = _erros_godot(saida)
    if erros:
        return "Rodou COM ERROS de runtime:\n" + "\n".join(erros)[:5000]
    return (f"OK — rodou {frames} frames sem erros de runtime.\n" +
            (saida[-1200:] if saida else "(sem saída relevante)"))


def godot_screenshot(cena: str = "", frames: int = 90) -> str:
    """RODA o jogo/uma cena e RENDERIZA a imagem do que aparece na tela (na GPU),
    guardando o último frame como screenshot que a interface exibe. Use pra 'ver'
    o resultado visual do que você programou. 'cena' é o caminho de uma .tscn
    (ex: 'Arenas/arena.tscn'); vazio = cena principal. 'frames' = quantos quadros
    rodar antes de capturar (mais frames = cena mais 'adiantada')."""
    if not _GODOT_BIN:
        return "ERRO: nenhum binário do Godot configurado (godot_bin no config.json)."
    if not (_WORKDIR / "project.godot").is_file():
        return "ERRO: a pasta atual não é um projeto Godot (sem project.godot)."
    frames = max(1, min(int(frames), 600))
    tmp = tempfile.mkdtemp(prefix="alice_shot_")
    prefixo = os.path.join(tmp, "f.png")
    cmd = [_GODOT_BIN, "--path", str(_WORKDIR), "--write-movie", prefixo, "--quit-after", str(frames)]
    if cena:
        cmd.append(cena)
    try:
        r = subprocess.run(cmd, cwd=str(_WORKDIR), capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return "Screenshot excedeu o tempo limite (120s)."
    pngs = sorted(glob.glob(os.path.join(tmp, "f*.png")))
    saida = (r.stdout + r.stderr)
    if not pngs:
        shutil.rmtree(tmp, ignore_errors=True)
        erros = _erros_godot(saida)
        return ("Screenshot falhou — nenhum frame renderizado (cena tem tela? "
                "há cena principal?).\n" + ("\n".join(erros)[:2000] if erros else saida[-1500:]))
    try:
        shutil.copyfile(pngs[-1], str(ULTIMO_SCREENSHOT))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    msg = f"📸 Screenshot renderizado do jogo rodando ({len(pngs)}º frame) — a interface está exibindo a imagem."
    erros = _erros_godot(saida)
    if erros:
        msg += "\n⚠️ Erros de runtime durante a execução:\n" + "\n".join(erros)[:1500]
    return msg


LOCAL_TOOLS = [read_file, list_dir, write_file, search_code, run_command,
               check_godot_syntax, godot_project_info, godot_rodar,
               godot_screenshot, lembrar]
