import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import {
  isWebAuthnSupported,
  hasStoredPasskey,
  authenticateWithPasskey,
} from '../lib/webauthn';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [showPasskeyOption, setShowPasskeyOption] = useState(false);
  const { login, loginWithToken } = useAuth();
  const navigate = useNavigate();

  // Check if passkey is available on mount
  useEffect(() => {
    const checkPasskey = async () => {
      if (isWebAuthnSupported() && hasStoredPasskey()) {
        setShowPasskeyOption(true);
      }
    };
    checkPasskey();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await login(email, password);
    setLoading(false);

    if (result.success) {
      navigate('/dashboard');
    } else {
      setError(result.error || 'Login failed');
    }
  };

  const handlePasskeyLogin = async () => {
    setError('');
    setPasskeyLoading(true);

    // Get stored email or use a default user ID
    const storedEmail = localStorage.getItem('boswell_user_email') || 'steve';
    
    const result = await authenticateWithPasskey(storedEmail);
    setPasskeyLoading(false);

    if (result.success && result.token) {
      // Use the token to complete login
      const loginResult = await loginWithToken(result.token);
      if (loginResult.success) {
        navigate('/dashboard');
      } else {
        setError(loginResult.error || 'Login failed');
      }
    } else {
      setError(result.error || 'Face ID authentication failed');
    }
  };

  return (
    <div className="min-h-screen bg-ink-950 flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="mb-10 reveal">
        <img src="/boswell-logo-dark.svg" alt="Boswell" className="h-12 w-12 mx-auto" />
      </div>

      {/* Tagline */}
      <div className="text-center mb-8 reveal delay-1">
        <p className="text-parchment-200/50 text-sm uppercase tracking-widest mb-2">Memory for AI</p>
        <h1 className="font-display text-4xl text-parchment-50">
          Welcome back
        </h1>
      </div>

      {/* Face ID / Passkey Button */}
      {showPasskeyOption && (
        <div className="w-full max-w-sm mb-6 reveal delay-2">
          <button
            type="button"
            onClick={handlePasskeyLogin}
            disabled={passkeyLoading}
            className="w-full py-3.5 bg-ink-900/50 hover:bg-ink-800/50 border border-parchment-200/20 hover:border-parchment-200/40 text-parchment-50 font-medium rounded-full transition-all disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-3"
          >
            {passkeyLoading ? (
              <>
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Authenticating...</span>
              </>
            ) : (
              <>
                {/* Face ID Icon */}
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                  <rect x="3" y="3" width="18" height="18" rx="3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>Sign in with Face ID</span>
              </>
            )}
          </button>
          
          <div className="flex items-center my-6">
            <div className="flex-1 border-t border-parchment-200/10" />
            <span className="px-4 text-parchment-200/30 text-sm">or</span>
            <div className="flex-1 border-t border-parchment-200/10" />
          </div>
        </div>
      )}

      {/* Form */}
      <form 
        onSubmit={handleSubmit} 
        className="w-full max-w-sm reveal delay-2"
      >
        {error && (
          <div className="mb-6 p-4 bg-red-950/50 border border-red-900/30 rounded-xl text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full bg-ink-900/50 border border-parchment-200/10 rounded-xl px-4 py-3 text-parchment-50 placeholder-parchment-200/30 focus:border-ember-500/50 transition-colors"
            />
          </div>

          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="Password"
              className="w-full bg-ink-900/50 border border-parchment-200/10 rounded-xl px-4 py-3 text-parchment-50 placeholder-parchment-200/30 focus:border-ember-500/50 transition-colors"
            />
          </div>
        </div>

        <div className="mt-2 text-right">
          <Link to="/forgot-password" className="text-sm text-parchment-200/40 hover:text-ember-500 transition-colors">
            Forgot password?
          </Link>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-6 py-3.5 bg-ember-500 hover:bg-ember-400 disabled:opacity-50 text-ink-950 font-medium rounded-full transition-all disabled:cursor-not-allowed group inline-flex items-center justify-center gap-2"
        >
          {loading ? 'Signing in...' : 'Sign in'}
          {!loading && (
            <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          )}
        </button>

        <p className="mt-6 text-center text-parchment-200/40 text-sm">
          Don't have an account?{' '}
          <Link to="/signup" className="text-ember-500 hover:text-ember-400">
            Sign up
          </Link>
        </p>
      </form>
    </div>
  );
}
