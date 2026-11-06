import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { IndividualUsersAdminPanel } from './IndividualUsersAdminPanel';

describe('Individual User Management', () => {
  it('offers a Create user button to the admin', () => {
    const html = renderToStaticMarkup(<IndividualUsersAdminPanel />);
    expect(html).toContain('Create user');
  });
});
