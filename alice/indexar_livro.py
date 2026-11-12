"""Indexa um PDF de regras para a ferramenta `consultar_regra`.

    python -m alice.indexar_livro "C:/caminho/Tormenta20.pdf" [apelido]

Extrai o texto página a página para dados/livros/<apelido>.json. O arquivo fica
só na sua máquina (a pasta `dados/` está no .gitignore) — o livro é seu, o
índice é para consulta pessoal na mesa.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from alice import armazenamento as arm
from alice.config import carregar


def indexar(pdf: Path, apelido: str, pasta: Path) -> int:
    from pypdf import PdfReader
    paginas = []
    for n, pagina in enumerate(PdfReader(str(pdf)).pages, 1):
        texto = re.sub(r"[ \t]+", " ", pagina.extract_text() or "").strip()
        if len(texto) > 80:
            paginas.append({"pagina": n, "texto": texto})
    arm.gravar(pasta / f"{apelido}.json", paginas)
    return len(paginas)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pdf = Path(sys.argv[1])
    apelido = sys.argv[2] if len(sys.argv) > 2 else re.sub(r"[^a-z0-9]+", "-", pdf.stem.lower()).strip("-")
    n = indexar(pdf, apelido, Path(carregar().pasta_livros))
    print(f"{n} páginas indexadas em '{apelido}'.")
