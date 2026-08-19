from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_FILES = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

errors: list[str] = []

for markdown_file in MARKDOWN_FILES:
    text = markdown_file.read_text(encoding="utf-8")

    for raw_target in LINK_RE.findall(text):
        target = raw_target.strip()

        if not target:
            continue

        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue

        # Ignore an optional Markdown title after a path.
        if ' "' in target:
            target = target.split(' "', 1)[0]

        target = unquote(target)

        # Remove an anchor before checking the filesystem path.
        path_part = target.split("#", 1)[0]

        if not path_part:
            continue

        resolved = (markdown_file.parent / path_part).resolve()

        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(
                f"{markdown_file.relative_to(ROOT)} -> "
                f"{target}: escapes repository root"
            )
            continue

        if not resolved.exists():
            errors.append(
                f"{markdown_file.relative_to(ROOT)} -> "
                f"{target}: target does not exist"
            )

if errors:
    print("Broken local documentation links:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)

print(
    f"Documentation links OK "
    f"({len(MARKDOWN_FILES)} Markdown files checked)."
)
