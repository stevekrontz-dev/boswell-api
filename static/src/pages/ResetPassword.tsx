import { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';

const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/v2/auth/password-reset/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password })
      });
      const data = await res.json();

      if (res.ok) {
        setSuccess(true);
        setTimeout(() => navigate('/login'), 3000);
      } else {
        setError(data.error || 'Failed to reset password');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center">
          <div className="text-5xl mb-6">🔗</div>
          <h1 className="text-2xl font-display text-parchment-50 mb-4">Invalid reset link</h1>
          <p className="text-parchment-200/60 mb-8">
            This password reset link is invalid or has expired.
          </p>
          <Link
            to="/forgot-password"
            className="text-ember-500 hover:text-ember-400 transition-colors"
          >
            Request a new reset link
          </Link>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center">
          <div className="text-5xl mb-6">✓</div>
          <h1 className="text-2xl font-display text-parchment-50 mb-4">Password reset!</h1>
          <p className="text-parchment-200/60 mb-8">
            Your password has been updated. Redirecting to login...
          </p>
          <Link
            to="/login"
            className="text-ember-500 hover:text-ember-400 transition-colors"
          >
            Go to login now
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-display text-parchment-50 mb-2">Set new password</h1>
          <p className="text-parchment-200/60">Enter your new password below</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-parchment-200/60 mb-2">New password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-4 py-3 bg-ink-900 border border-parchment-200/10 rounded-lg text-parchment-50 placeholder-parchment-200/30 focus:outline-none focus:border-ember-500/50"
              placeholder="At least 8 characters"
            />
          </div>

          <div>
            <label className="block text-sm text-parchment-200/60 mb-2">Confirm password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-4 py-3 bg-ink-900 border border-parchment-200/10 rounded-lg text-parchment-50 placeholder-parchment-200/30 focus:outline-none focus:border-ember-500/50"
              placeholder="Enter password again"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-ember-500 hover:bg-ember-400 disabled:bg-ember-500/50 text-ink-950 font-medium rounded-lg transition-colors"
          >
            {loading ? 'Resetting...' : 'Reset password'}
          </button>
        </form>
      </div>
    </div>
  );
}
