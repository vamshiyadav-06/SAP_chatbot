import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LanguageCard } from './LanguageCard';
import { ANSWER_LANGUAGES } from './answerLanguages';

describe('LanguageCard', () => {
  it('offers English and many other languages, with the current one selected', () => {
    const html = renderToStaticMarkup(<LanguageCard value="hi" onChanged={() => {}} />);
    expect(html).toContain('Answer language');
    expect(html).toContain('<option value="hi" selected');
    expect(html).toContain('<option value="en"');
    expect(ANSWER_LANGUAGES.length).toBeGreaterThanOrEqual(10);
    expect(new Set(ANSWER_LANGUAGES.map((l) => l.code)).size).toBe(ANSWER_LANGUAGES.length);
  });
});
