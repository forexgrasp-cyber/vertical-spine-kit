# Vertical Spine Kit

Snapford vertical SaaS scaffold. FastAPI backend + React SPA, wired to
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

      python -m shared.webui.design_conformance https://vertical-spine-kit.snapford.com

## Quickstart

    git clone <this repo> vertical-spine-kit
    cd vertical-spine-kit
    py -3.12 -m venv .venv
    .venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
    .venv\Scripts\pip install -e ..\shared-canonical-services
    py -3.12 -m pytest tests -q

    cd frontend && npm install && npm run dev   # :24581
    py -3.12 -m uvicorn main:app --port 8163 --reload

## Before first deploy

1. Register the product in `shared/branding/product_registry.py`
   (copy an existing `ProductEntry`; set `theme_key='vertical-spine-kit'`).
2. Pick/extend the vertical theme in `shared/webui/vertical_themes.py`
   (unknown keys fall back to the neutral platform blue).
3. Translate product-specific strings:
   `set PROSE_BACKEND=gemini` then `py -3.12 scripts/build_locales.py`.
4. Deploy: `docker compose -f docker-compose.satellite.yml up -d --build`
   (needs `.env`, sibling shared checkout, Traefik `web` network).
