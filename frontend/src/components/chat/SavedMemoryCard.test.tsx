import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SavedMemoryCard } from './SavedMemoryCard';

describe('SavedMemoryCard', () => {
  it('explains how to save and who can see it', () => {
    const html = renderToStaticMarkup(<SavedMemoryCard />);
    expect(html).toContain('Saved memory');
    expect(html).toContain('save it');
    expect(html).toContain('only you can see them');
  });
});
