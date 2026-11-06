import React, { useState } from 'react';
import { Languages } from 'lucide-react';
import { apiSetLanguage, apiSetQuestionLanguage } from '../../services/api';
import { ANSWER_LANGUAGES } from './answerLanguages';

interface LanguageCardProps {
  value: string;
  onChanged: (code: string) => void;
  /** Language questions are asked in; '' means the same as the answer language. */
  questionValue?: string;
  onQuestionChanged?: (code: string | null) => void;
}

const SELECT_STYLE: React.CSSProperties = {
  display: 'block', marginTop: 6, padding: '6px 10px', borderRadius: 8, border: '1px solid #cbd5e1',
  background: 'transparent', color: 'inherit',
};

const optionLabel = ({ english, native }: { english: string; native: string }) =>
  native === english ? english : `${native} (${english})`;

/** Settings: the language answers are written in and the language questions are asked in. */
export const LanguageCard: React.FC<LanguageCardProps> = ({ value, onChanged, questionValue = '', onQuestionChanged }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeQuestion = async (code: string) => {
    setBusy(true);
    setError(null);
    try {
      const user = await apiSetQuestionLanguage(code || null);
      onQuestionChanged?.(user.question_language ?? null);
    } catch {
      setError('Could not change the language. Please try again.');
    } finally {
      setBusy(false);
    }
  };

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
          Choose the language you ask in and the language answers are written in. SAP terms such as transaction
          codes and table names stay as they are.
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
            style={SELECT_STYLE}
          >
            {ANSWER_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>{optionLabel(lang)}</option>
            ))}
          </select>
          <label htmlFor="question-language" style={{ display: 'block', marginTop: 16 }}>
            <strong>Question language</strong>
          </label>
          <select
            id="question-language"
            value={questionValue}
            disabled={busy}
            onChange={(e) => changeQuestion(e.target.value)}
            style={SELECT_STYLE}
          >
            <option value="">Same as answer language</option>
            {ANSWER_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>{optionLabel(lang)}</option>
            ))}
          </select>
          {error && <span role="alert">{error}</span>}
        </div>
      </div>
    </div>
  );
};
