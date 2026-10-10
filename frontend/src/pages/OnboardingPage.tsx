import React, { useState } from 'react';
import { ArrowRight, CalendarDays } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { BrandLogo } from '../components/navbar/BrandLogo';
import { PageMeta } from '../components/ui/PageMeta';
import { useAuth } from '../context/AuthContext';

export const OnboardingPage: React.FC = () => {
  const { user, updateProfile } = useAuth();
  const [name, setName] = useState(user?.name || '');
  const [dateOfBirth, setDateOfBirth] = useState(user?.dateOfBirth || '');
  const [validationError, setValidationError] = useState('');
  const navigate = useNavigate();

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidationError('');
    const normalizedName = name.trim();

    if (!normalizedName) {
      setValidationError('Enter your full name to continue.');
      return;
    }

    updateProfile({ name: normalizedName, dateOfBirth });
    navigate('/app', { replace: true });
  };

  return (
    <>
      <PageMeta
        title="Complete Your Profile"
        description="Add your name and preferences to set up your Clyptusap.ai profile."
      />
      <main className="login-layout">
        <section className="login-panel onboarding-panel">
          <div className="login-brand">
            <BrandLogo />
          </div>
          <Link to="/" className="login-back">
            Clyptusap.ai
          </Link>
          <div className="login-card onboarding-card">
            <span className="eyebrow">ONE QUICK STEP</span>
            <h1>
              Complete your<br />profile
            </h1>
            <p>Set up your workspace display name to get started.</p>

            <form className="onboarding-form" onSubmit={submit} noValidate>
              <label htmlFor="full-name">Full name</label>
              <input
                id="full-name"
                name="name"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={120}
                placeholder="e.g. Senior SAP BRIM Consultant"
              />

              <label htmlFor="date-of-birth">Date of birth (Optional)</label>
              <div className="date-input-wrap">
                <input
                  id="date-of-birth"
                  name="dateOfBirth"
                  type="date"
                  value={dateOfBirth}
                  onChange={(event) => setDateOfBirth(event.target.value)}
                />
                <CalendarDays size={16} aria-hidden="true" />
              </div>

              {validationError && (
                <p className="form-error" role="alert">
                  {validationError}
                </p>
              )}

              <button className="button button-dark onboarding-submit cursor-pointer" type="submit">
                Continue to Clyptusap.ai <ArrowRight size={16} />
              </button>
            </form>
          </div>
        </section>
      </main>
    </>
  );
};
