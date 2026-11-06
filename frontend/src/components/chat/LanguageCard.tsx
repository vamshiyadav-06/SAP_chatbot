import React, { useState } from 'react';
import { Languages } from 'lucide-react';
import { apiSetLanguage } from '../../services/api';
import { ANSWER_LANGUAGES } from './answerLanguages';

/** Settings: the language answers are written in. Questions can be asked in that language or in English. */
export const LanguageCard: React.FC<{ value: string; onChanged: (code: string) => void }> = ({ value, onChanged }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const change = async (code: string) => {
    setBusy(true);
    setError(null);
    try {
      const user = await apiSetLanguage(code);
      onChanged(user.preferred_language ?? code);
    } catch {
      setError('Could not change the language. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-group">
      <div className="settings-group-heading">
        <h2>Language</h2>
        <p>
          Ask in your language or in English. Answers are written in the language you choose here. SAP terms such
          as transaction codes and table names stay as they are.
        </p>
      </div>
      <div className="settings-row">
        <div className="settings-row-icon">
          <span className="account-avatar" aria-hidden="true"><Languages size={14} /></span>
        </div>
        <div style={{ flex: 1 }}>
          <label htmlFor="answer-language"><strong>Answer language</strong></label>
          <select
            id="answer-language"
            value={value}
            disabled={busy}
            onChange={(e) => change(e.target.value)}
            style={{ display: 'block', marginTop: 6, padding: '6px 10px', borderRadius: 8, border: '1px solid #cbd5e1', background: 'transparent', color: 'inherit' }}
          >
            {ANSWER_LANGUAGES.map(({ code, english, native }) => (
              <option key={code} value={code}>
                {native === english ? english : `${native} (${english})`}
              </option>
            ))}
          </select>
          {error && <span role="alert">{error}</span>}
        </div>
      </div>
    </div>
  );
};
