import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

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
