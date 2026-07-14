#!/usr/bin/env python3
# ============================================================
#  instalar_plugin.py — instala o plugin da Alice num projeto Godot
#
#  Uso:
#      python instalar_plugin.py "/caminho/do/projeto/godot"
#
#  Copia addons/alice para o projeto e habilita no project.godot.
#  Depois, no editor: Projeto → Recarregar Projeto Atual.
#  (e o servidor da Alice precisa estar rodando: python -m frontends.webui)
# ============================================================
import os
import sys
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(BASE, "godot-plugin", "addons", "alice")
PLUGIN_RES = "res://addons/alice/plugin.cfg"


def habilitar(project_godot: str) -> str:
    """Garante que o plugin está na lista enabled do [editor_plugins]."""
    with open(project_godot, encoding="utf-8") as f:
        linhas = f.read().splitlines()

    if any(PLUGIN_RES in l for l in linhas):
        return "já estava habilitado"

    # acha a seção [editor_plugins]
    sec = next((i for i, l in enumerate(linhas) if l.strip() == "[editor_plugins]"), None)

    if sec is None:
        if linhas and linhas[-1].strip() != "":
            linhas.append("")
        linhas += ["[editor_plugins]", "", f'enabled=PackedStringArray("{PLUGIN_RES}")']
        return _gravar(project_godot, linhas, "seção criada + habilitado")

    # procura 'enabled=' dentro da seção (até a próxima seção)
    j = sec + 1
    enabled = None
    while j < len(linhas) and not linhas[j].strip().startswith("["):
        if linhas[j].strip().startswith("enabled="):
            enabled = j
            break
        j += 1

    if enabled is None:
        linhas.insert(sec + 1, f'enabled=PackedStringArray("{PLUGIN_RES}")')
    else:
        l = linhas[enabled]
        fecha = l.rfind(")")
        antes = l[:fecha].rstrip()
        sep = "" if antes.endswith("(") else ", "
        linhas[enabled] = f'{antes}{sep}"{PLUGIN_RES}"{l[fecha:]}'
    return _gravar(project_godot, linhas, "habilitado")


def _gravar(caminho: str, linhas: list, msg: str) -> str:
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return msg


def main():
    if len(sys.argv) < 2:
        print('uso: python instalar_plugin.py "/caminho/do/projeto/godot"')
        sys.exit(1)
    proj = sys.argv[1]
    pg = os.path.join(proj, "project.godot")
    if not os.path.isfile(pg):
        print(f"❌ não encontrei project.godot em: {proj}")
        sys.exit(1)
    if not os.path.isdir(ORIGEM):
        print(f"❌ plugin de origem não encontrado: {ORIGEM}")
        sys.exit(1)

    destino = os.path.join(proj, "addons", "alice")
    shutil.copytree(ORIGEM, destino, dirs_exist_ok=True)
    print(f"✅ plugin copiado → {destino}")
    print(f"✅ project.godot: {habilitar(pg)}")
    print("\nPronto! No editor: Projeto → Recarregar Projeto Atual (o dock 'Alice' aparece à direita).")
    print("Lembrete: o servidor precisa estar no ar → python -m frontends.webui")


if __name__ == "__main__":
    main()
