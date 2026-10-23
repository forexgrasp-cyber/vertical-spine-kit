import { useEffect, useState } from 'react';
import { LangSelect, ThemeToggle } from '@shared/widgets';
import { loadTranslations, t } from './i18n';

export default function App() {
  const [lang, setLang] = useState('en');

  const handleLangChange = (code: string) => {
    setLang(code);
    localStorage.setItem('language', code);
    void loadTranslations(code);
  };

  useEffect(() => {
    void loadTranslations(lang);
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Vertical Spine Kit</span>
        <div className="controls">
          <LangSelect value={lang} onChange={handleLangChange} />
          <ThemeToggle />
        </div>
      </header>
      <main>
        <h1>{t('nav.dashboard')}</h1>
        <p>{t('common.loading')}</p>
      </main>
    </div>
  );
}
