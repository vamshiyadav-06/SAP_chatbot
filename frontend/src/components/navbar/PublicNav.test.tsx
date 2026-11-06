import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { PublicNav } from './PublicNav';

const renderAt = (path: string) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <PublicNav />
    </MemoryRouter>,
  );

const html = renderAt('/');

const linksIn = (markup: string, label: string) =>
  [...markup.matchAll(/<a[^>]*href="([^"]*)"[^>]*>([^<]*)</g)]
    .filter(([, , text]) => text.trim() === label)
    .map(([, href]) => href.replace(/&amp;/g, '&'));

const linksTo = (label: string) => linksIn(html, label);

describe('PublicNav', () => {
  it('does not offer individual registration when the build flag is off', () => {
    expect(linksTo('Sign up')).toEqual([]);
  });

  it('sends Sign in to the sign-in tab, desktop and mobile', () => {
    expect(linksTo('Sign in')).toEqual(['/login?mode=login', '/login?mode=login']);
  });

  it('on organisation pages, signs in to the organisation and offers Request access instead of Sign up', () => {
    for (const path of ['/organisation', '/organisation/login', '/organisation/activate']) {
      const markup = renderAt(path);
      expect(linksIn(markup, 'Sign in')).toEqual(['/organisation/login', '/organisation/login']);
      expect(linksIn(markup, 'Request access')).toEqual(['/organisation#request', '/organisation#request']);
      expect(linksIn(markup, 'Sign up')).toEqual([]);
    }
  });

  it('links to the Organisation Portal', () => {
    expect(linksTo('Organisation')).toEqual(['/organisation']);
  });

  it('no longer offers Try now', () => {
    expect(html).not.toContain('Try now');
  });

  it('shows the logo plainly, not as a highlighted button', () => {
    expect(html).not.toContain('brand-highlighted');
    expect(html).toContain('aria-label="Clyptusap.ai home"');
  });

  it('makes the logo shine with a decorative glint masked to the logo', () => {
    expect(html).toContain('brand-shine');
    expect(html).toMatch(/<span class="brand-shine-glint" aria-hidden="true" style="--logo-mask:url\([^)]+\)"/);
  });
});
