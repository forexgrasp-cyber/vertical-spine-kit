# CallAgent

Voice AI for Local Businesses. FastAPI backend + React SPA, wired to
the canonical shared services from day one.

## Platform surfaces (already wired)

- **SEO surfaces** (`shared.web.seo_surfaces`): `/sitemap.xml`,
  `/robots.txt`, `/api/seo/manifest`, `/api/seo/style/tokens.css`
  (generated light+dark design tokens for this product's vertical theme).
- **i18n**: `/api/i18n/languages` (20 platform locales, native names,
  rtl dirs) + `/api/i18n/translations/{lang}` backed by `locales/`.
- **Shell widgets** (`shared.widgets.react`): `ThemeToggle` + `LangSelect`
  via the `@shared/widgets` path alias into the sibling
  `shared-canonical-services` checkout.
- **Design conformance**: `tests/test_scaffold.py` runs
  `shared.webui.design_conformance.audit_product` against the generated
  app; the same audit works against the deployed URL:

      python -m shared.webui.design_conformance https://callagent.snapford.com

## Quickstart

    git clone <this repo> callagent
    cd callagent
    py -3.12 -m venv .venv
    .venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
    .venv\Scripts\pip install -e ..\shared-canonical-services
    py -3.12 -m pytest tests -q

    cd frontend && npm install && npm run dev   # :24581
    py -3.12 -m uvicorn main:app --port 8163 --reload

## Before first deploy

1. Register the product in `shared/branding/product_registry.py`
   (copy an existing `ProductEntry`; set `theme_key='callagent'`).
2. Pick/extend the vertical theme in `shared/webui/vertical_themes.py`
   (unknown keys fall back to the neutral platform blue).
3. Translate product-specific strings:
   `set PROSE_BACKEND=gemini` then `py -3.12 scripts/build_locales.py`.

## Deployment (shared VPS estate)

The estate deploys itself: a daily watcher on the box (cron 07:17 UTC) pulls
`main`, the sibling shared checkout, builds, gates and rolls back. A push is
picked up by the next watcher run - no Actions minutes, no manual steps.

- **Deploy script**: `deploy/vps/deploy.sh` is GENERATED from
  `deploy/vps/render.json` (`shared.deployment.DeployService`) - never
  hand-edit it. Re-render/prove sync:
  `SHARED_CANONICAL_SERVICES=../shared-canonical-services python scripts/check_deploy_generated.py --write`
- **One-time server setup** (on the VPS): `bash deploy/vps/server_bootstrap.sh`
  (deploy key + clone + `.env` scaffold + watcher site-list line).
  `FIRST_DEPLOY=1` prefix runs the first deploy too.
- **Manual re-run**: `ssh vps 'bash /opt/sites/scripts/deploy_watcher.sh callagent'`
  or the `workflow_dispatch`-only `.github/workflows/deploy-vps.yml`.
- **Gates**: loopback health (`http://127.0.0.1:8163/api/health`, 90s) then
  public surface gate (`robots.txt`, `sitemap.xml` markers); failure rolls
  back to the previous image automatically.
- **Local dev** (without the estate): `docker compose -f docker-compose.satellite.yml up -d --build`
  (needs `.env`, sibling shared checkout, Traefik `web` network).
