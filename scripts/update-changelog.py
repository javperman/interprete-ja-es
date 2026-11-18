#!/usr/bin/env python3
"""update-changelog.py — añade una entrada al registro de docs/CHANGELOG.md.

Gestiona el bloque ``<!-- AUTO-LOG:START --> … <!-- AUTO-LOG:END -->``.
No borres ni reescribas ese bloque a mano; usa este script.

Uso:
    python3 scripts/update-changelog.py \
      --task "Descripción del cambio" \
      --files "src/interprete/audio/nodes.py, docs/plans/fase-0-grafo-audio.md" \
      --sources "https://wiki.archlinux.org/title/PipeWire, comprobación local" \
      --notes "Conclusión o decisión"

La fecha se toma en ISO 8601 (hora local).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

START = "<!-- AUTO-LOG:START -->"
END = "<!-- AUTO-LOG:END -->"
DEFAULT_CHANGELOG = Path(__file__).resolve().parent.parent / "docs" / "CHANGELOG.md"


def _cell(value: str) -> str:
    """Normaliza una celda de tabla markdown (sin saltos ni barras)."""
    text = " ".join((value or "").split())
    return text.replace("|", "\\|")


def append_entry(changelog: Path, task: str, files: str, sources: str, notes: str) -> None:
    content = changelog.read_text(encoding="utf-8")
    if START not in content or END not in content:
        raise SystemExit(f"No encuentro los marcadores AUTO-LOG en {changelog}")

    row = "| {date} | {task} | {files} | {sources} | {notes} |".format(
        date=dt.date.today().isoformat(),
        task=_cell(task),
        files=_cell(files),
        sources=_cell(sources),
        notes=_cell(notes),
    )

    pattern = re.compile(re.escape(START) + r"(.*?)" + re.escape(END), re.DOTALL)
    match = pattern.search(content)
    if not match:  # pragma: no cover - cubierto por la comprobación previa
        raise SystemExit("Bloque AUTO-LOG mal formado")

    body = match.group(1).rstrip("\n")
    new_block = f"{START}{body}\n{row}\n{END}"
    changelog.write_text(content[: match.start()] + new_block + content[match.end():], encoding="utf-8")
    print(f"Entrada añadida a {changelog}:\n{row}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Añade una entrada al CHANGELOG.")
    parser.add_argument("--task", required=True, help="Descripción breve del cambio")
    parser.add_argument("--files", default="", help="Ficheros tocados (separados por comas)")
    parser.add_argument("--sources", default="", help="Fuentes oficiales / comprobaciones")
    parser.add_argument("--notes", default="", help="Conclusión o decisión")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    args = parser.parse_args(argv)

    append_entry(args.changelog, args.task, args.files, args.sources, args.notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
