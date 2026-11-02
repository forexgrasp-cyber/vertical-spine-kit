"""Prove deploy/vps/deploy.sh matches render.json; --write re-renders.

Canonical scheme (DEPLOYMENT_PLAYBOOK.md section 5): deploy scripts are
GENERATED from shared.deployment.DeployService using the inputs in
deploy/vps/render.json. A hand edit is lost at the next render.

Usage (from the repo root, sibling shared checkout assumed):

    SHARED_CANONICAL_SERVICES=../shared-canonical-services \\
        python scripts/check_deploy_generated.py            # prove sync
    SHARED_CANONICAL_SERVICES=../shared-canonical-services \\
        python scripts/check_deploy_generated.py --write    # re-render

Note the env var name: SHARED_CANONICAL_SERVICES (the shared repo root).
With the wrong name the script silently falls back to the sibling checkout -
or to whatever `shared` package is installed in the interpreter (incident 9.1).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = ROOT / "deploy" / "vps" / "render.json"


def _load_service():
    """Import DeployService from the checkout named by the env var (fallback: sibling)."""
    env_path = os.environ.get("SHARED_CANONICAL_SERVICES", "")
    for candidate in (env_path, str(ROOT.parent / "shared-canonical-services")):
        if candidate and (Path(candidate) / "shared" / "deployment" / "deploy_service.py").is_file():
            sys.path.insert(0, str(Path(candidate).resolve()))
            break
    else:
        # Fall back to the installed shared package (last resort - warn loudly).
        print("WARN: no SHARED_CANONICAL_SERVICES checkout found; using installed shared package", file=sys.stderr)
    module = importlib.import_module("shared.deployment.deploy_service")
    return module.DeployService()


def main() -> int:
    parser = argparse.ArgumentParser(description="deploy.sh render sync check")
    parser.add_argument("--write", action="store_true", help="re-render deploy.sh from render.json")
    args = parser.parse_args()

    spec = json.loads(RENDER.read_text(encoding="utf-8"))
    deploy_args = spec["deploy"]["args"]
    target = ROOT / "deploy" / "vps" / deploy_args.get("file", "deploy.sh")

    service = _load_service()
    rendered = service.render_deploy_script(**deploy_args)

    if args.write:
        target.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"rendered {target.relative_to(ROOT)}")
        return 0

    current = target.read_text(encoding="utf-8")
    if current == rendered:
        print(f"OK: {target.relative_to(ROOT)} matches render.json")
        return 0

    print(f"STALE: {target.relative_to(ROOT)} does not match render.json", file=sys.stderr)
    print("re-render with: python scripts/check_deploy_generated.py --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
