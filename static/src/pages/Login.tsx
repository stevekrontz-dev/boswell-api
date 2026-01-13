import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Logo from '../components/Logo';

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
    <div className="min-h-screen bg-boswell-bg flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="mb-10 animate-fade-in">
        <Logo size="lg" />
      </div>

      {/* Tagline */}
      <div className="text-center mb-8 animate-slide-up">
        <h1 className="font-display text-3xl md:text-4xl text-white mb-2">
          Welcome back
        </h1>
        <p className="text-gray-500 font-body">
          Sign in to access your memory
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
              placeholder="Enter your password"
              className="w-full bg-boswell-bg-secondary border border-boswell-border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-ember-500 transition-colors"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-8 py-3.5 bg-ember-500 hover:bg-ember-400 disabled:bg-boswell-border disabled:text-gray-500 text-boswell-bg font-semibold rounded-full transition-all duration-200 hover:shadow-glow-sm"
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>

        <p className="mt-6 text-center text-gray-500 text-sm">
          Don't have an account?{' '}
          <Link to="/signup" className="text-ember-500 hover:text-ember-400 transition-colors">
            Sign up
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
