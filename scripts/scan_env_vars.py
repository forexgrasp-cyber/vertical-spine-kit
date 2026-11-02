"""Scan the repo for os.getenv/os.environ reads and print the sorted var names."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = (
    re.compile(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\.get\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\[\s*[\"']([A-Z0-9_]+)[\"']\s*\]"),
)

names: set[str] = set()
for f in ROOT.rglob("*.py"):
    s = str(f)
    if ".venv" in s or "node_modules" in s or "frontend" in s:
        continue
    text = f.read_text(encoding="utf-8", errors="ignore")
    for pat in PATTERNS:
        names.update(pat.findall(text))

print("\n".join(sorted(names)))
