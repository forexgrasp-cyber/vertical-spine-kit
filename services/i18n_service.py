"""Thin product wrapper over the shared i18n string storage + registry.

Public language codes are the platform 20; metadata (native names, rtl)
resolves through the shared locale registry - never hand-rolled lists.
"""

from __future__ import annotations

from pathlib import Path

from shared.i18n import dir_for, locale_info, registry_code_for
from shared.i18n.string_storage import StringStorage

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
_DEFAULT_LANGUAGE = "en"
_NAMESPACE = "app"


class I18nService:
    def __init__(
        self,
        locales_dir: Path = _LOCALES_DIR,
        default_language: str = _DEFAULT_LANGUAGE,
    ) -> None:
        self.locales_dir = Path(locales_dir)
        self.default_language = default_language
        self._storage = StringStorage(
            locales_dir=str(self.locales_dir), default_locale=default_language
        )
        self._storage.load()

    def get_supported_languages(self) -> dict[str, str]:
        """code -> native name, for every shipped locale dir."""
        return {
            code: locale_info(registry_code_for(code)).native
            for code in self._shipped()
        }

    def dir(self, language: str | None) -> str:
        """Text direction ("ltr"/"rtl") via the shared locale registry."""
        return dir_for(registry_code_for(self._coerce(language)))

    def translations(self, language: str) -> dict[str, str]:
        """Raw string table for a language (namespace "app")."""
        table = self._storage.get_locale_namespace(self._coerce(language), _NAMESPACE)
        return dict(table or {})

    def _shipped(self) -> list[str]:
        if not self.locales_dir.exists():
            return [self.default_language]
        return sorted(
            p.parent.name for p in self.locales_dir.glob("*/app.json")
        )

    def _coerce(self, language: str | None) -> str:
        if not language:
            return self.default_language
        code = language.lower()
        shipped = self._shipped()
        if code in shipped:
            return code
        base = code.split("-")[0]
        if base in shipped:
            return base
        return self.default_language
