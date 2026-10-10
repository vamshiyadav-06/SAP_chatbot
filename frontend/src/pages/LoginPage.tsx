import React, { useState, useEffect } from 'react';
import { ArrowLeft, ArrowRight, ShieldCheck, Mail, Lock, User, Sparkles, AlertCircle } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { BrandLogo } from '../components/navbar/BrandLogo';
import { PageMeta } from '../components/ui/PageMeta';
import { useAuth } from '../context/AuthContext';

export const LoginPage: React.FC = () => {
  const { user, login, register, guestLogin } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [mode, setMode] = useState<'login' | 'register'>(() => {
    return searchParams.get('mode') === 'register' ? 'register' : 'login';
  });

  useEffect(() => {
    const urlMode = searchParams.get('mode');
    if (urlMode === 'register' || urlMode === 'login') {
      setMode(urlMode);
    }
  }, [searchParams]);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect to workspace
  React.useEffect(() => {
    if (user) {
      navigate('/app', { replace: true });
    }
  }, [user, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === 'login') {
        await login(email.trim(), password);
      } else {
        if (!name.trim()) throw new Error('Please enter your full name');
        await register(name.trim(), email.trim(), password);
      }
      navigate('/app', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials or try Demo Access.');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoAccess = async () => {
    setLoading(true);
    try {
      await guestLogin();
      navigate('/app', { replace: true });
    } catch {
      navigate('/app', { replace: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageMeta
        title="Sign In"
        description="Continue to your Clyptusap.ai knowledge workspace."
      />
      <main className="login-layout">
        <section className="login-panel">
          <div className="login-brand">
            <BrandLogo />
          </div>

          <Link to="/" className="login-back">
            <ArrowLeft size={15} /> Back to home
          </Link>

          <div className="login-card">
            <span className="eyebrow">SAP + BRIM KNOWLEDGE ASSISTANT</span>
            <h1>
              Welcome to<br />
              Clyptusap.ai
            </h1>
            <p>Your intelligent SAP knowledge workspace</p>

            {/* Mode Switcher */}
            <div className="flex rounded-xl bg-slate-200/60 dark:bg-slate-800 p-1 mb-5 text-xs font-semibold">
              <button
                type="button"
                onClick={() => { setMode('login'); setError(null); }}
                className={`flex-1 py-2 rounded-lg transition ${
                  mode === 'login'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setMode('register'); setError(null); }}
                className={`flex-1 py-2 rounded-lg transition ${
                  mode === 'register'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                }`}
              >
                Create Account
              </button>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200 dark:bg-rose-950/60 dark:border-rose-800 text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2 text-left">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3 text-left">
              {mode === 'register' && (
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                    <input
                      type="text"
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="SAP Consultant"
                      className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-orange-500"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="consultant@sap-enterprise.com"
                    className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-orange-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-orange-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="button button-dark w-full mt-4 flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>{loading ? 'Authenticating...' : mode === 'login' ? 'Sign In to Workspace' : 'Create Workspace Account'}</span>
                <ArrowRight size={14} />
              </button>
            </form>

            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200 dark:border-slate-700" />
              </div>
              <div className="relative flex justify-center text-[10px] uppercase tracking-wider text-slate-400">
                <span className="bg-[#f8f8f6] dark:bg-[#191a18] px-2">or quick access</span>
              </div>
            </div>

            {/* Quick Demo Access */}
            <button
              type="button"
              onClick={handleDemoAccess}
              className="button button-outline w-full flex items-center justify-center gap-2 border-dashed border-slate-400 hover:border-slate-600 transition cursor-pointer"
            >
              <Sparkles size={14} className="text-orange-500" />
              <span>Instant Test Drive (1-Click Guest)</span>
            </button>

            <div className="login-safe">
              <ShieldCheck size={15} />
              <span>
                Enterprise Security &amp; JWT isolation<br />
                <small>Connected to FastAPI &amp; PostgreSQL/SQLite RAG backend</small>
              </span>
            </div>
          </div>

          <div className="login-legal">
            <span>Powered by sentence-transformers &amp; cross-encoder reranking.</span>
            <Link to="/features">Explore Clyptusap.ai</Link>
          </div>
        </section>
      </main>
    </>
  );
};
