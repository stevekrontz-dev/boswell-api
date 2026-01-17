import { useState } from 'react';
import { Link } from 'react-router-dom';

const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${API_BASE}/v2/auth/password-reset/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();

      if (res.ok) {
        setSent(true);
      } else {
        setError(data.error || 'Failed to send reset email');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center">
          <div className="text-5xl mb-6">📧</div>
          <h1 className="text-2xl font-display text-parchment-50 mb-4">Check your email</h1>
          <p className="text-parchment-200/60 mb-8">
            If an account exists with <span className="text-parchment-50">{email}</span>,
            you'll receive a password reset link shortly.
          </p>
          <Link
            to="/login"
            className="text-ember-500 hover:text-ember-400 transition-colors"
          >
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-display text-parchment-50 mb-2">Reset your password</h1>
          <p className="text-parchment-200/60">Enter your email and we'll send you a reset link</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-parchment-200/60 mb-2">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 bg-ink-900 border border-parchment-200/10 rounded-lg text-parchment-50 placeholder-parchment-200/30 focus:outline-none focus:border-ember-500/50"
              placeholder="you@example.com"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-ember-500 hover:bg-ember-400 disabled:bg-ember-500/50 text-ink-950 font-medium rounded-lg transition-colors"
          >
            {loading ? 'Sending...' : 'Send reset link'}
          </button>
        </form>

        <p className="text-center mt-6 text-parchment-200/40 text-sm">
          Remember your password?{' '}
          <Link to="/login" className="text-ember-500 hover:text-ember-400">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
