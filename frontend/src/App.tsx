import { useEffect, useState, useCallback } from 'react';
import { LangSelect, ThemeToggle } from '@shared/widgets';
import { loadTranslations, t } from './i18n';

type License = {
  key: string;
  holder: string;
  issued_at: number;
  revoked: boolean;
};

type ApiError = { detail?: string };

function apiHeaders(licenseKey?: string) {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (licenseKey) h['X-License-Key'] = licenseKey;
  return h;
}

async function api<T>(path: string, opts: RequestInit = {}, licenseKey?: string): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    ...opts,
    headers: { ...apiHeaders(licenseKey), ...opts.headers },
  });
  if (!resp.ok) {
    const err = (await resp.json().catch(() => ({}))) as ApiError;
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export default function App() {
  const [lang, setLang] = useState('en');
  const [licenseKey, setLicenseKey] = useState('');
  const [verifyInput, setVerifyInput] = useState('');
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; key?: string; holder?: string; issued_at?: number } | null>(null);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [mintHolder, setMintHolder] = useState('');
  const [newKey, setNewKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'valid' | 'invalid' | 'none'>('none');

  const handleLangChange = (code: string) => {
    setLang(code);
    localStorage.setItem('language', code);
    void loadTranslations(code);
  };

  useEffect(() => {
    void loadTranslations(lang);
    void loadLicenses();
  }, [lang]);

  const loadLicenses = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api<{ licenses: License[] }>('/licenses', {}, licenseKey || undefined);
      setLicenses(data.licenses);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load licenses');
    } finally {
      setLoading(false);
    }
  }, [licenseKey]);

  const handleMint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mintHolder.trim()) return;
    try {
      setLoading(true);
      const data = await api<{ key: string; holder: string; issued_at: number }>('/licenses/mint', {
        method: 'POST',
        body: JSON.stringify({ holder: mintHolder }),
      });
      setNewKey(data.key);
      setLicenses((prev) => [...prev, { key: data.key, holder: data.holder, issued_at: data.issued_at, revoked: false }]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mint license');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!verifyInput.trim()) return;
    try {
      setLoading(true);
      const data = await api<{ valid: boolean; key: string; holder: string; issued_at: number }>('/licenses/verify', {
        method: 'POST',
        body: JSON.stringify({ key: verifyInput }),
      });
      setVerifyResult({ valid: data.valid, key: data.key, holder: data.holder, issued_at: data.issued_at });
      setStatus(data.valid ? 'valid' : 'invalid');
      setError(null);
    } catch (err) {
      setStatus('invalid');
      setError(err instanceof Error ? err.message : 'Invalid license key');
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (key: string) => {
    if (!window.confirm(`Revoke license ${key}?`)) return;
    try {
      setLoading(true);
      await api(`/licenses/${encodeURIComponent(key)}/revoke`, { method: 'POST' }, licenseKey || undefined);
      setLicenses((prev) => prev.map((l) => (l.key === key ? { ...l, revoked: true } : l)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke license');
    } finally {
      setLoading(false);
    }
  };

  const isValid = status === 'valid';
  const hasActiveLicense = licenses.some((l) => !l.revoked);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="logo">VSK</span>
          <span className="name">Vertical Spine Kit</span>
        </div>
        <div className="controls">
          <div className="license-input">
            <label htmlFor="license-key">License Key</label>
            <input
              id="license-key"
              type="text"
              placeholder="VSK-...."
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
              disabled={loading}
              className="license-input"
            />
            <button
              type="button"
              onClick={() => {
                void loadLicenses();
              }}
              disabled={loading || !licenseKey}
              className="btn btn-sm"
            >
              Apply
            </button>
          </div>
          <LangSelect value={lang} onChange={handleLangChange} />
          <ThemeToggle />
        </div>
      </header>

      <main>
        {!isValid && !hasActiveLicense ? (
          <section className="card gate">
            <h2>{t('nav.license_required')}</h2>
            <p>{t('license.enter_key')}</p>
            <form onSubmit={handleVerify} className="verify-form">
              <input
                type="text"
                placeholder="VSK-...."
                value={verifyInput}
                onChange={(e) => setVerifyInput(e.target.value)}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !verifyInput.trim()} className="btn">
                {t('license.verify')}
              </button>
            </form>
            {verifyResult && (
              <div className={`result ${verifyResult.valid ? 'result-ok' : 'result-bad'}`}>
                {verifyResult.valid ? (
                  <>
                    <span className="badge ok">✓ Valid</span>
                    <p>
                      <strong>{verifyResult.holder}</strong> &middot; issued{' '}
                      {new Date(verifyResult.issued_at! * 1000).toLocaleDateString()}
                    </p>
                  </>
                ) : (
                  <>
                    <span className="badge bad">✗ Invalid</span>
                    <p>{t('license.invalid')}</p>
                  </>
                )}
              </div>
            )}
            {error && <p className="error">{error}</p>}
          </section>
        ) : (
          <>
            <section className="card stats">
              <div className="stat">
                <span className="stat-value">{licenses.length}</span>
                <span className="stat-label">{t('license.total_keys')}</span>
              </div>
              <div className="stat">
                <span className="stat-value">{licenses.filter((l) => !l.revoked).length}</span>
                <span className="stat-label">{t('license.active_keys')}</span>
              </div>
              <div className="stat">
                <span className="stat-value">{licenses.filter((l) => l.revoked).length}</span>
                <span className="stat-label">{t('license.revoked_keys')}</span>
              </div>
            </section>

            <section className="card mint-card">
              <h2>{t('license.create_key')}</h2>
              <form onSubmit={handleMint} className="mint-form">
                <input
                  type="text"
                  placeholder={t('license.holder_placeholder')}
                  value={mintHolder}
                  onChange={(e) => setMintHolder(e.target.value)}
                  disabled={loading}
                />
                <button type="submit" disabled={loading || !mintHolder.trim()} className="btn btn-primary">
                  {t('license.mint')}
                </button>
              </form>
              {newKey && (
                <div className="new-key">
                  <span className="badge ok">✓ {t('license.created')}</span>
                  <code>{newKey}</code>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(newKey);
                    }}
                    className="btn btn-sm"
                  >
                    {t('license.copy')}
                  </button>
                </div>
              )}
            </section>

            <section className="card list-card">
              <h2>{t('license.your_keys')}</h2>
              {licenses.length === 0 ? (
                <p className="empty">{t('license.no_keys')}</p>
              ) : (
                <table className="license-table">
                  <thead>
                    <tr>
                      <th>{t('license.key')}</th>
                      <th>{t('license.holder')}</th>
                      <th>{t('license.issued')}</th>
                      <th>{t('license.status')}</th>
                      <th>{t('license.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {licenses.map((l) => (
                      <tr key={l.key} className={l.revoked ? 'revoked' : ''}>
                        <td>
                          <code>{l.key}</code>
                        </td>
                        <td>{l.holder || '—'}</td>
                        <td>{new Date(l.issued_at * 1000).toLocaleDateString()}</td>
                        <td>
                          <span className={`badge ${l.revoked ? 'bad' : 'ok'}`}>
                            {l.revoked ? t('license.revoked') : t('license.active')}
                          </span>
                        </td>
                        <td>
                          {!l.revoked && (
                            <button
                              type="button"
                              onClick={() => void handleRevoke(l.key)}
                              disabled={loading}
                              className="btn btn-sm btn-danger"
                            >
                              {t('license.revoke')}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
        {error && <p className="error">{error}</p>}
      </main>
    </div>
  );
}

declare global {
  interface Window {
    __VSK_LICENSE_KEY__?: string;
  }
}