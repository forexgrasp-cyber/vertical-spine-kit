"""/api/i18n routes: supported languages + raw translation tables."""

from __future__ import annotations

from fastapi import APIRouter

from services.i18n_service import I18nService

router = APIRouter(prefix="/api/i18n", tags=["i18n"])

_i18n = I18nService()


@router.get("/languages")
async def get_supported_languages() -> dict:
    """Supported languages (code -> native name) plus text directions."""
    languages = _i18n.get_supported_languages()
    return {
        "languages": languages,
        "default": _i18n.default_language,
        "dirs": {code: _i18n.dir(code) for code in languages},
    }


@router.get("/translations/{language}")
async def get_translations(language: str) -> dict:
    return {
        "language": language,
        "translations": _i18n.translations(language),
        "fallback": _i18n.default_language,
        "dir": _i18n.dir(language),
    }
