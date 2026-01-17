import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await register(email, password, name, agreedToTerms);
    setLoading(false);

    if (result.success) {
      navigate('/dashboard');
    } else {
      setError(result.error || 'Registration failed');
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
          Get started
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
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Your name"
              className="w-full bg-ink-900/50 border border-parchment-200/10 rounded-xl px-4 py-3 text-parchment-50 placeholder-parchment-200/30 focus:border-ember-500/50 transition-colors"
            />
          </div>

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
              minLength={8}
              placeholder="Password (8+ characters)"
              className="w-full bg-ink-900/50 border border-parchment-200/10 rounded-xl px-4 py-3 text-parchment-50 placeholder-parchment-200/30 focus:border-ember-500/50 transition-colors"
            />
          </div>

          {/* Terms */}
          <div className="flex items-start gap-3 pt-2">
            <input
              type="checkbox"
              id="terms"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              required
              className="mt-1 w-4 h-4 rounded border-parchment-200/20 bg-ink-900 text-ember-500 focus:ring-ember-500 focus:ring-offset-0"
            />
            <label htmlFor="terms" className="text-sm text-parchment-200/60">
              I agree to the{' '}
              <a href="/legal/terms" target="_blank" className="text-ember-500 hover:text-ember-400">
                Terms of Service
              </a>{' '}
              and{' '}
              <a href="/legal/privacy" target="_blank" className="text-ember-500 hover:text-ember-400">
                Privacy Policy
              </a>
            </label>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !agreedToTerms}
          className="w-full mt-6 py-3.5 bg-ember-500 hover:bg-ember-400 disabled:bg-ember-600 disabled:opacity-50 text-ink-950 font-medium rounded-full transition-all disabled:cursor-not-allowed group inline-flex items-center justify-center gap-2"
        >
          {loading ? 'Creating account...' : 'Create account'}
          {!loading && (
            <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          )}
        </button>

        <p className="mt-6 text-center text-parchment-200/40 text-sm">
          Already have an account?{' '}
          <Link to="/login" className="text-ember-500 hover:text-ember-400">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
