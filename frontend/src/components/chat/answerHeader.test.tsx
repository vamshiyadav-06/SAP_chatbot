import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { Message } from '../../types';

const auth = vi.hoisted(() => ({ user: null as { is_admin: boolean } | null }));
vi.mock('../../context/AuthContext', () => ({ useAuth: () => auth }));

const { ChatMessage } = await import('./ChatMessage');
const { GroundingScoreBadge } = await import('./GroundingScoreBadge');

const answer = (overrides: Partial<Message> = {}): Message => ({
  id: '7f1c2a9e-0000-4000-8000-000000000002',
  chat_id: 'c1',
  role: 'assistant',
  content: 'Convergent Invoicing groups billable items into billing documents.',
  created_at: '2026-11-03T10:00:00Z',
  citations: [],
  web_sources: [],
  regeneration_count: 1,
  token_usage: { used: 400, baseline: 1600, saved: 1200, cost: 0.07 },
  ...overrides,
});

const render = (message: Message) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <ChatMessage message={message} onRegenerate={() => {}} />
    </MemoryRouter>,
  );

/** The classes of the nearest `tag` element with a class that opens before `marker` (`skip` moves further out). */
const classBefore = (html: string, marker: string, tag: 'span' | 'div' | 'button', skip = 0) => {
  const at = html.indexOf(marker);
  expect(at).toBeGreaterThan(-1);
  const opening = [...html.matchAll(new RegExp(`<${tag}\\b[^>]*\\bclass="([^"]*)"`, 'g'))].filter(
    (match) => match.index! < at,
  );
  return opening[opening.length - 1 - skip][1].split(/\s+/);
};

describe('answer header', () => {
  it('shows "Regeneration #n" as a one-line pill shaped like the other header badges', () => {
    const badge = classBefore(render(answer()), 'Regeneration #', 'span');
    expect(badge).toEqual(expect.arrayContaining(['rounded-full', 'px-2.5', 'gap-1.5', 'whitespace-nowrap', 'shrink-0']));
    expect(badge).not.toContain('rounded');
  });

  it('keeps the tokens-used badge level with the first line when the badges wrap', () => {
    const html = render(answer());
    // Row: top-aligned, so a second line of badges does not pull the right-hand badge down.
    expect(classBefore(html, '>Clyptus.AI</span>', 'div', 1)).toContain('items-start');
    expect(classBefore(html, '>Clyptus.AI</span>', 'div', 1)).not.toContain('items-center');
    // The name and the saved badge both sit in a 24px first line, centred the same way.
    expect(classBefore(html, '>Clyptus.AI</span>', 'span')).toContain('leading-6');
    expect(html).toMatch(/<div class="flex h-6 shrink-0 items-center"><span title="[^"]*" aria-label="You used only/);
  });

  it('gives the admin grounding badge the same text size as the other badges', () => {
    // index.css sets button{font:inherit} outside any layer, which beats Tailwind's text size
    // utilities on a <button>; the size therefore goes on the label inside it.
    const html = renderToStaticMarkup(<GroundingScoreBadge score={0.82} verificationStatus="verified" />);
    const button = classBefore(html, 'Grounding:', 'button');
    expect(button).not.toContain('text-xs');
    expect(classBefore(html, 'Grounding:', 'span')).toEqual(expect.arrayContaining(['text-xs', 'font-semibold']));
  });

  it('still shows the admin badges next to the regeneration badge', () => {
    auth.user = { is_admin: true };
    try {
      const html = render(answer({ source_type: 'knowledge_base', grounding_score: 0.82, verification_status: 'verified' }));
      expect(html.indexOf('Regeneration #')).toBeLessThan(html.indexOf('Grounding:'));
    } finally {
      auth.user = null;
    }
  });
});
