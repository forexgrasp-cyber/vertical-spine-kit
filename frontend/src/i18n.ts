let translations: Record<string, string> = {};

export function t(key: string): string {
  return translations[key] || key;
}

export async function loadTranslations(lang: string): Promise<void> {
  try {
    const resp = await fetch(`/api/i18n/translations/${lang}`);
    if (resp.ok) {
      const data = await resp.json();
      translations = data.translations || {};
      document.documentElement.lang = lang;
      document.documentElement.dir = data.dir || 'ltr';
      return;
    }
  } catch {
    // backend not running (pure frontend dev) - fall through to defaults
  }
  translations = {};
  document.documentElement.lang = lang;
  document.documentElement.dir = 'ltr';
}
