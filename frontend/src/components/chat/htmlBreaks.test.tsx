import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnswerMarkdown } from './AnswerMarkdown';

const TABLE = [
  '| Step | Action |',
  '|---|---|',
  '| 2. Install | - SAP S/4HANA (incl. FI‑CA) <br> - SAP Convergent Charging <br/> - SAP Convergent Invoicing |',
].join('\n');

describe('<br> in answers', () => {
  it('becomes a real line break inside table cells, never literal text', () => {
    const html = renderToStaticMarkup(<AnswerMarkdown content={TABLE} />);
    expect(html).not.toContain('&lt;br');
    expect(html).not.toContain('<br>-');
    expect(html.match(/<br\/>/g)).toHaveLength(2);
    expect(html).toContain('SAP Convergent Charging');
  });

  it('still does not render other raw HTML', () => {
    const html = renderToStaticMarkup(<AnswerMarkdown content={'Hello <script>alert(1)</script> <b>x</b>'} />);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<b>');
  });

  it('removes stray <t>-style tags from table rows instead of showing them', () => {
    const table = [
      '| Step | Action |',
      '|---|---|',
      '| 1 | <t>Plan the landscape</t> <td>on-premise</td> |',
      '| 2 | <li>Install S/4HANA<li>Install Charging |',
    ].join('\n');
    const html = renderToStaticMarkup(<AnswerMarkdown content={table} />);
    expect(html).not.toMatch(/&lt;\/?(t|td|li)&gt;/);
    expect(html).toContain('Plan the landscape');
    expect(html).toContain('• Install S/4HANA');
  });

  it('leaves placeholders such as <tcode> in normal text alone', () => {
    const html = renderToStaticMarkup(<AnswerMarkdown content={'Run `<tcode>` and enter <t> as given.'} />);
    expect(html).toContain('&lt;tcode&gt;');
  });
});
