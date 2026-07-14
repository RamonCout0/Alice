#!/usr/bin/env bash
# Liga a Alice na interface web (abre sozinha no navegador).
# Pode dar duplo-clique no atalho da Área de trabalho ou rodar direto no terminal.
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" -m frontends.webui "${1:-7861}"
