"""JSON em disco com escrita atômica (nunca deixa arquivo pela metade)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_trava = threading.Lock()


def ler(caminho: Path, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return padrao() if callable(padrao) else padrao


def gravar(caminho: Path, dados) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with _trava:
        fd, tmp = tempfile.mkstemp(dir=caminho.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, caminho)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
