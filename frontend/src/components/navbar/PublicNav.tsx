import React, { useState } from 'react';
import { Menu, X } from 'lucide-react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { BrandLogo } from './BrandLogo';
import { ORG_LOGIN_PATH, ORG_PORTAL_PATH } from '../../layouts/accountRouting';

// The login page opens the matching tab from ?mode=.
const INDIVIDUAL_ACTIONS = {
  signIn: '/login?mode=login',
  primary: { to: '/login?mode=register', label: 'Sign up' },
};

// On the Organisation Portal pages, "Sign in" means the organisation sign-in, and organisations do not
// sign up: they request an account and receive an activation code.
const ORGANISATION_ACTIONS = {
  signIn: ORG_LOGIN_PATH,
  primary: { to: `${ORG_PORTAL_PATH}#request`, label: 'Request access' },
};
const PUBLIC_REGISTRATION_ENABLED = import.meta.env.VITE_REGISTRATION_ENABLED?.toLowerCase() === 'true';

export const PublicNav: React.FC = () => {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const actions = pathname.startsWith(ORG_PORTAL_PATH)
    ? ORGANISATION_ACTIONS
    : PUBLIC_REGISTRATION_ENABLED
      ? INDIVIDUAL_ACTIONS
      : { signIn: INDIVIDUAL_ACTIONS.signIn };

  return (
    <header className="public-nav">
      <div className="nav-inner">
        <BrandLogo size="xl" shine />
        <button
          className="icon-button mobile-menu-toggle"
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          onClick={() => setOpen(!open)}
        >
          {open ? <X size={19} /> : <Menu size={19} />}
        </button>
        <nav className={`nav-links ${open ? 'nav-links-open' : ''}`} aria-label="Main navigation">
          <NavLink to="/features" onClick={() => setOpen(false)}>Features</NavLink>
          <NavLink to="/how-it-works" onClick={() => setOpen(false)}>How it works</NavLink>
          <NavLink to="/organisation" onClick={() => setOpen(false)}>Organisation</NavLink>
          <a href="/#about" onClick={() => setOpen(false)}>About</a>
          <a href="/#faq" onClick={() => setOpen(false)}>FAQ</a>
          <div className="mobile-nav-actions">
            <Link className="nav-signin" to={actions.signIn} onClick={() => setOpen(false)}>Sign in</Link>
            {'primary' in actions && <Link className="button button-brand button-small" to={actions.primary.to} onClick={() => setOpen(false)}>
              {actions.primary.label}
            </Link>}
          </div>
        </nav>
        <div className="nav-actions">
          <Link className="nav-signin" to={actions.signIn}>Sign in</Link>
          {'primary' in actions && <Link className="button button-brand button-small" to={actions.primary.to}>
            {actions.primary.label}
          </Link>}
        </div>
      </div>
    </header>
  );
};
