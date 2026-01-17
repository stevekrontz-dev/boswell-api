import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Logo from '../components/Logo';

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
    <div className="min-h-screen bg-boswell-bg flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="mb-10 animate-fade-in">
        <Logo size="lg" />
      </div>

      {/* Tagline */}
      <div className="text-center mb-8 animate-slide-up">
        <h1 className="font-display text-3xl md:text-4xl text-white mb-2">
          Get started
        </h1>
        <p className="text-gray-500 font-body">
          Create your Boswell account
        </p>
      </div>

      {/* Form Card */}
      <form 
        onSubmit={handleSubmit} 
        className="w-full max-w-sm bg-boswell-card rounded-2xl p-8 border border-boswell-border animate-slide-up"
        style={{ animationDelay: '0.1s' }}
      >
        {error && (
          <div className="mb-6 p-4 bg-red-950/50 border border-red-900/50 rounded-xl text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Your name"
              className="w-full bg-boswell-bg-secondary border border-boswell-border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-ember-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full bg-boswell-bg-secondary border border-boswell-border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-ember-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="At least 8 characters"
              className="w-full bg-boswell-bg-secondary border border-boswell-border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-ember-500 transition-colors"
            />
          </div>

          {/* Terms Agreement */}
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              id="terms"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              required
              className="mt-1 w-4 h-4 rounded border-boswell-border bg-boswell-bg-secondary text-ember-500 focus:ring-ember-500 focus:ring-offset-0"
            />
            <label htmlFor="terms" className="text-sm text-gray-400">
              I agree to the{' '}
              <a href="/legal/terms" target="_blank" className="text-ember-500 hover:text-ember-400 transition-colors">
                Terms of Service
              </a>{' '}
              and{' '}
              <a href="/legal/privacy" target="_blank" className="text-ember-500 hover:text-ember-400 transition-colors">
                Privacy Policy
              </a>
            </label>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !agreedToTerms}
          className="w-full mt-8 py-3.5 bg-ember-500 hover:bg-ember-400 disabled:bg-gray-700 disabled:text-gray-400 text-boswell-bg font-semibold rounded-full transition-all duration-200 hover:shadow-glow-sm disabled:cursor-not-allowed"
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>

        <p className="mt-6 text-center text-gray-500 text-sm">
          Already have an account?{' '}
          <Link to="/login" className="text-ember-500 hover:text-ember-400 transition-colors">
            Sign in
          </Link>
        </p>
      </form>

      {/* Footer */}
      <p className="mt-10 text-gray-600 text-xs animate-fade-in" style={{ animationDelay: '0.3s' }}>
        Memory for your AI
      </p>
    </div>
  );
}
