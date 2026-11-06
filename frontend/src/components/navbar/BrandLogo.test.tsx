import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { BrandLogo } from './BrandLogo';

const render = (node: React.ReactNode) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

describe('BrandLogo', () => {
  it('leads to the landing page by default (public pages)', () => {
    expect(render(<BrandLogo />)).toContain('href="/"');
  });
  it('can lead somewhere else, so the signed-in app keeps the user in the app', () => {
    const html = render(<BrandLogo to="/app" />);
    expect(html).toContain('href="/app"');
    expect(html).not.toContain('href="/"');
  });
});
