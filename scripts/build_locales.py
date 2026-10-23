"""Translate locales/en/app.json into every platform locale.

Requires a translation backend (see shared/i18n/prose.py):
    set PROSE_BACKEND=gemini   (or: argos)
    py -3.12 scripts/build_locales.py

Paced + retried; a locale whose failure rate is high is SKIPPED (never
write an English-fallback catalog to disk).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_sibling = ROOT.parent / "shared-canonical-services"
if _sibling.exists():  # dev convenience; no-op when shared is installed
    sys.path.insert(0, str(_sibling))

from shared.i18n import PLATFORM_LOCALES  # noqa: E402
from shared.i18n.prose import translate_text  # noqa: E402

NAMESPACE = "app"
GAP_SECONDS = 3.5
RETRIES = 3


def main() -> int:
    locales_dir = ROOT / "locales"
    en_path = locales_dir / "en" / f"{NAMESPACE}.json"
    en = json.loads(en_path.read_text(encoding="utf-8"))
    failures: dict[str, int] = {}
    for code in PLATFORM_LOCALES:
        if code == "en":
            continue
        out: dict[str, str] = {}
        bad = 0
        for key, source in en.items():
            result = None
            for _attempt in range(RETRIES):
                result = translate_text(source, code)
                cleaned = (result or "").strip()
                if cleaned and cleaned != source:
                    break
                time.sleep(GAP_SECONDS)
            cleaned = (result or "").strip()
            if cleaned:
                out[key] = cleaned
            else:
                bad += 1
            time.sleep(GAP_SECONDS)
        if bad > max(1, len(en) // 4):
            failures[code] = bad
            print(f"SKIP {code}: {bad}/{len(en)} failed (not writing)")
            continue
        out_path = locales_dir / code / f"{NAMESPACE}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"ok {code}: {len(out)} keys")
    if failures:
        print(f"failed locales: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
