# ============================================================
#  core/tools.py — ferramentas locais da Alice (as "mãos")
#  Todas escopadas ao diretório do projeto (workdir) por segurança.
# ============================================================
import os
import re
import pathlib
import subprocess

_WORKDIR: pathlib.Path = pathlib.Path(".").resolve()
_CONFIRM = None  # callback(cmd: str) -> bool ; definido pelo frontend

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


def configure(workdir: str = ".", confirm_cb=None):
    """Define a raiz do projeto e o callback de confirmação de comandos."""
    global _WORKDIR, _CONFIRM
    _WORKDIR = pathlib.Path(workdir).resolve()
    _CONFIRM = confirm_cb


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


LOCAL_TOOLS = [read_file, list_dir, write_file, search_code, run_command]
