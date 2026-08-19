from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SPANISH_DOCS = DOCS / "es"

START_MARKER = "<!-- DOC_NAV_START -->"
END_MARKER = "<!-- DOC_NAV_END -->"

TARGETS_EN = {
    "Project README": ROOT / "README.md",
    "Docs index": DOCS / "README.md",
    "Findings": DOCS / "findings" / "cubicacion_accuracy_problem.md",
    "Experiments": DOCS / "experiments",
    "Decisions": DOCS / "decisions",
    "Spanish docs": SPANISH_DOCS / "README.md",
    "Estado técnico": SPANISH_DOCS / "estado-proyecto.md",
    "Preguntas Campo Digital": SPANISH_DOCS / "preguntas-campo-digital.md",
}

TARGETS_ES = {
    "README del proyecto": ROOT / "README.md",
    "Índice de documentación": DOCS / "README.md",
    "Hallazgos": DOCS / "findings" / "cubicacion_accuracy_problem.md",
    "Experimentos": DOCS / "experiments",
    "Decisiones": DOCS / "decisions",
    "Documentación en español": SPANISH_DOCS / "README.md",
    "Estado técnico": SPANISH_DOCS / "estado-proyecto.md",
    "Preguntas Campo Digital": SPANISH_DOCS / "preguntas-campo-digital.md",
}


def relative_link(source: Path, target: Path) -> str:
    return os.path.relpath(target, source.parent).replace(os.sep, "/")


def is_spanish_document(path: Path) -> bool:
    return path == SPANISH_DOCS or SPANISH_DOCS in path.parents


def build_navigation(path: Path) -> str:
    spanish = is_spanish_document(path)
    targets = TARGETS_ES if spanish else TARGETS_EN
    heading = "### Navegación de documentación" if spanish else "### Documentation navigation"

    links: list[str] = []

    for label, target in targets.items():
        if target.resolve() == path.resolve():
            continue

        links.append(f"[{label}]({relative_link(path, target)})")

    return f"{START_MARKER}\n\n---\n\n{heading}\n\n" + " · ".join(links) + f"\n\n{END_MARKER}"


def main() -> None:
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )

    updated: list[Path] = []

    for path in sorted(DOCS.rglob("*.md")):
        if "templates" in path.parts:
            continue

        # docs/README.md has its own top-level navigation bar.
        if path == DOCS / "README.md":
            continue

        text = path.read_text(encoding="utf-8").rstrip()
        navigation = build_navigation(path)

        if pattern.search(text):
            new_text = pattern.sub(navigation, text)
        else:
            new_text = text + "\n\n" + navigation

        path.write_text(new_text + "\n", encoding="utf-8")
        updated.append(path)

    print(f"Documentation navigation updated in {len(updated)} files.")

    for path in updated:
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
