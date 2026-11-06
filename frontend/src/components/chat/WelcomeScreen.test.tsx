import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { WelcomeScreen } from './WelcomeScreen';
import { MODES, SUGGESTIONS } from './welcomeContent';
import type { ChatMode } from '../../types';

const render = (mode: ChatMode) =>
  renderToStaticMarkup(<WelcomeScreen mode={mode} onModeChange={() => {}} onSelectPrompt={() => {}} />);

describe('WelcomeScreen', () => {
  it('has a single High button that is pressed only in High mode', () => {
    const high = render('scholar');
    const low = render('sprint');

    expect(high.match(/<button[^>]*aria-label="High mode"/g)).toHaveLength(1);
    expect(high).toContain('aria-pressed="true"');
    expect(low).toContain('aria-pressed="false"');
    expect(low).not.toContain('>Low</button>');
  });

  it.each<ChatMode>(['sprint', 'scholar'])('shows the %s suggestions only', (mode) => {
    const other: ChatMode = mode === 'sprint' ? 'scholar' : 'sprint';
    const html = render(mode);

    for (const { title } of SUGGESTIONS[mode]) expect(html).toContain(title);
    for (const { title } of SUGGESTIONS[other]) {
      if (!SUGGESTIONS[mode].some((s) => s.title === title)) expect(html).not.toContain(title);
    }
  });

  it('sets SAP-only expectations and explains both modes', () => {
    const html = render('sprint');

    expect(html).not.toContain('Ask any question');
    expect(html).toContain('SAP BRIM');
    expect(html).toContain(MODES[0].detail); // the chosen mode is explained under the switch
    expect(render('scholar')).toContain(MODES[1].detail);
    expect(html).toContain('AI answers can contain mistakes');
  });

  it('offers distinct, SAP-specific prompts', () => {
    const prompts = [...SUGGESTIONS.sprint, ...SUGGESTIONS.scholar].map((s) => s.prompt);

    expect(new Set(prompts).size).toBe(prompts.length);
    for (const prompt of prompts) expect(prompt).toMatch(/SAP|BRIM|FI-CA|Convergent/);
  });
});
