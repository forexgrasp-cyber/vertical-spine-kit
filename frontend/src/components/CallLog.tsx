"""Call Log dashboard component - lists tenant voice calls with Twilio recording playback."""

import { useEffect, useState } from 'react';

type CallRecord = {
  id: string;
  call_sid: string;
  tenant_id: string;
  from_number: string;
  to_number: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  recording_url: string | null;
  recording_sid: string | null;
  intent: string | null;
  confidence: number | null;
  extracted_fields: string | null;
  consent_granted: boolean;
  created_at: string | null;
};

type ExtractedFields = {
  service?: string | null;
  datetime?: string | null;
  address?: string | null;
  callback_phone?: string | null;
};

export default function CallLog({ tenantId }: { tenantId: string }) {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/v1/agent/${encodeURIComponent(tenantId)}/calls?limit=100`)
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
      })
      .then((data: { calls: CallRecord[] }) => {
        if (!cancelled) {
          setCalls(data.calls || []);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load calls');
          setCalls([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  const parseFields = (raw: string | null): ExtractedFields => {
    if (!raw) return {};
    try {
      return JSON.parse(raw) as ExtractedFields;
    } catch {
      return {};
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
  };

  const formatDuration = (sec: number | null) => {
    if (!sec) return '—';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="call-log">
        <div className="spinner">Loading call log…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="call-log error">
        <p className="error-text">{error}</p>
      </div>
    );
  }

  return (
    <div className="call-log">
      <div className="call-log-header">
        <h2>Call Log</h2>
        <p className="subtitle">
          {calls.length} call{calls.length !== 1 ? 's' : ''} for tenant{' '}
          <strong>{tenantId}</strong>
        </p>
      </div>

      {calls.length === 0 ? (
        <div className="empty-state">
          <p>No calls recorded yet.</p>
          <p className="hint">
            Inbound Twilio calls to <code>/api/v1/agent/{tenantId}/webhook</code>
            will appear here.
          </p>
        </div>
      ) : (
        <table className="call-table">
          <thead>
            <tr>
              <th>Call SID</th>
              <th>From</th>
              <th>To</th>
              <th>Started</th>
              <th>Duration</th>
              <th>Intent</th>
              <th>Consent</th>
              <th>Recording</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((call) => {
              const fields = parseFields(call.extracted_fields);
              return (
                <tr key={call.call_sid} className={call.consent_granted ? '' : 'no-consent'}>
                  <td>
                    <code className="sid">{call.call_sid}</code>
                  </td>
                  <td>{call.from_number}</td>
                  <td>{call.to_number}</td>
                  <td>{formatDate(call.started_at)}</td>
                  <td>{formatDuration(call.duration_seconds)}</td>
                  <td>
                    {call.intent || '—'}
                    {call.confidence != null && (
                      <span className="confidence">
                        ({Math.round(call.confidence * 100)}%)
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`badge ${call.consent_granted ? 'ok' : 'bad'}`}>
                      {call.consent_granted ? 'Granted' : 'Denied'}
                    </span>
                  </td>
                  <td>
                    {call.recording_url ? (
                      <div className="recording-cell">
                        <audio controls src={call.recording_url} />
                        <br />
                        <a
                          href={call.recording_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-sm"
                        >
                          Open in Twilio
                        </a>
                      </div>
                    ) : (
                      <span className="dash">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="call-log-details">
          <h3>Extracted Fields</h3>
          {calls.length > 0 && (
            <ul className="fields-list">
              {calls
                .slice(0, 5)
                .map((call) => {
                  const f = parseFields(call.extracted_fields);
                  const hasFields =
                    f.service || f.datetime || f.address || f.callback_phone;
                  if (!hasFields) return null;
                  return (
                    <li key={call.call_sid} className="field-item">
                      <strong>{call.call_sid.slice(-8)}:</strong>{' '}
                      {f.service ? <span>Service: {f.service}</span> : null}
                      {f.datetime ? <span> | Time: {f.datetime}</span> : null}
                      {f.address ? <span> | Address: {f.address}</span> : null}
                      {f.callback_phone ? (
                        <span> | Callback: {f.callback_phone}</span>
                      ) : null}
                    </li>
                  );
                })
                .filter(Boolean)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
