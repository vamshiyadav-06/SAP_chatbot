import React, { useEffect, useState } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

type Appearance = 'light' | 'dark' | 'system';

export const SettingsPage: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [appearance, setAppearance] = useState<Appearance>(() => {
    const saved = localStorage.getItem('clyptus-appearance');
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'dark';
  });

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const updateTheme = () =>
      document.documentElement.classList.toggle(
        'dark',
        appearance === 'dark' || (appearance === 'system' && media.matches)
      );
    updateTheme();
    media.addEventListener('change', updateTheme);
    return () => media.removeEventListener('change', updateTheme);
  }, [appearance]);

  const chooseAppearance = (value: Appearance) => {
    setAppearance(value);
    localStorage.setItem('clyptus-appearance', value);
    window.dispatchEvent(new Event('theme-change'));
  };

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <section className="workspace-page settings-page">
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">MAKE YOUR SPACE YOURS</span>
          <h1>Settings</h1>
          <p>Manage your account and workspace preferences.</p>
        </div>
      </div>

      <div className="settings-group">
        <div className="settings-group-heading">
          <h2>Account</h2>
          <p>Your sign-in and account details.</p>
        </div>
        <div className="settings-row">
          <div className="settings-row-icon">
            <span className="account-avatar">
              {user?.name ? user.name.charAt(0).toUpperCase() : 'C'}
            </span>
          </div>
          <div>
            <strong>{user?.name || 'SAP Consultant'}</strong>
            <span>{user?.email || 'Enterprise User'}</span>
          </div>
          <span className="settings-placeholder">Active</span>
        </div>
      </div>

      <div className="settings-group">
        <div className="settings-group-heading">
          <h2>Appearance</h2>
          <p>Choose your preferred interface theme.</p>
        </div>
        <div className="appearance-options">
          {([
            ['light', Sun, 'Light'],
            ['dark', Moon, 'Dark'],
            ['system', Monitor, 'System'],
          ] as const).map(([value, Icon, title]) => (
            <button
              key={value}
              className={`appearance-option cursor-pointer ${appearance === value ? 'selected' : ''}`}
              onClick={() => chooseAppearance(value)}
            >
              <Icon size={17} />
              <span>{title}</span>
              {appearance === value && <i />}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-group logout-group">
        <div className="settings-group-heading">
          <h2>Sign out</h2>
          <p>Log out of your current session on this device.</p>
        </div>
        <button
          className="button button-outline button-small cursor-pointer"
          onClick={handleLogout}
        >
          Sign out
        </button>
      </div>
    </section>
  );
};
