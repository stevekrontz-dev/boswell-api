import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { getCurrentUser, createCheckoutSession, type UserProfile } from '../lib/api';

const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export default function Dashboard() {
  const { user: authUser } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const data = await getCurrentUser();
      setProfile(data);
    } catch (err) {
      console.error('Failed to load profile:', err);
    } finally {
      setLoading(false);
    }
  };

  const copyApiKey = () => {
    if (profile?.api_key) {
      navigator.clipboard.writeText(profile.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCheckout = async () => {
    setCheckoutLoading(true);
    try {
      const data = await createCheckoutSession('pro');
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      console.error('Checkout failed:', err);
    } finally {
      setCheckoutLoading(false);
    }
  };

  const downloadUrl = profile?.api_key
    ? `${API_BASE}/api/extension/download?api_key=${profile.api_key}`
    : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  // Show upgrade prompt if pending payment
  if (profile?.status === 'pending_payment') {
    return (
      <div className="space-y-8 animate-fade-in">
        <div className="text-center md:text-left">
          <h1 className="font-display text-3xl md:text-4xl text-white mb-2">
            Complete Your Setup
          </h1>
          <p className="text-gray-500 font-body">
            Subscribe to Boswell Pro to get started with your AI memory.
          </p>
        </div>

        <div className="bg-boswell-card rounded-2xl p-8 border border-boswell-border">
          <div className="max-w-xl mx-auto text-center">
            <div className="w-16 h-16 rounded-full bg-ember-glow flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
            <h2 className="font-display text-2xl text-white mb-4">Boswell Pro</h2>
            <p className="text-gray-400 mb-6">
              Unlimited memory for your Claude instances. Connect Claude Desktop, Claude Code, and Claude.ai
              with persistent context that never forgets.
            </p>
            <ul className="text-left text-gray-400 mb-8 space-y-2">
              <li className="flex items-center gap-2">
                <svg className="w-5 h-5 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                50,000 memories per month
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-5 h-5 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Unlimited branches (work, personal, projects)
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-5 h-5 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                5GB encrypted storage
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-5 h-5 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Priority support
              </li>
            </ul>
            <div className="text-3xl font-display text-white mb-6">
              $19<span className="text-lg text-gray-500">/month</span>
            </div>
            <button
              onClick={handleCheckout}
              disabled={checkoutLoading}
              className="w-full px-6 py-3 bg-ember-500 hover:bg-ember-400 disabled:bg-gray-700 text-boswell-bg font-semibold rounded-xl transition-colors"
            >
              {checkoutLoading ? 'Redirecting...' : 'Subscribe to Pro'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="text-center md:text-left">
        <h1 className="font-display text-3xl md:text-4xl text-white mb-2">
          Welcome back, <span className="text-ember-500">{profile?.name || authUser?.name || 'there'}</span>
        </h1>
        <p className="text-gray-500 font-body">
          Your Boswell memory is ready to use.
        </p>
      </div>

      {/* API Key Section */}
      {profile?.api_key && (
        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border">
          <h2 className="font-display text-xl text-white mb-4">Your API Key</h2>
          <div className="flex items-center gap-3">
            <code className="flex-1 bg-boswell-bg px-4 py-3 rounded-lg text-sm text-ember-400 font-mono break-all border border-boswell-border">
              {profile.api_key}
            </code>
            <button
              onClick={copyApiKey}
              className="px-4 py-3 bg-boswell-border hover:bg-boswell-border-light rounded-lg text-sm text-white transition-colors"
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <p className="text-gray-600 text-sm mt-3">
            Keep this key safe. You'll need it to connect your Claude instances.
          </p>
        </div>
      )}

      {/* Download Section */}
      <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border">
        <h2 className="font-display text-xl text-white mb-4">Install Boswell</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {downloadUrl && (
            <a
              href={downloadUrl}
              className="flex items-center gap-4 p-4 bg-boswell-bg rounded-xl border border-boswell-border hover:border-ember-500 transition-colors group"
            >
              <div className="w-12 h-12 rounded-full bg-ember-glow flex items-center justify-center group-hover:bg-ember-500/20 transition-colors">
                <svg className="w-6 h-6 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </div>
              <div>
                <div className="font-medium text-white">Claude Desktop</div>
                <div className="text-sm text-gray-500">Download .mcpb bundle</div>
              </div>
            </a>
          )}
          <a
            href="/connect"
            className="flex items-center gap-4 p-4 bg-boswell-bg rounded-xl border border-boswell-border hover:border-ember-500 transition-colors group"
          >
            <div className="w-12 h-12 rounded-full bg-ember-glow flex items-center justify-center group-hover:bg-ember-500/20 transition-colors">
              <svg className="w-6 h-6 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
            <div>
              <div className="font-medium text-white">Other Methods</div>
              <div className="text-sm text-gray-500">Claude Code, Claude.ai</div>
            </div>
          </a>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">Branches</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors">
            {profile?.usage?.branches ?? 0}
          </div>
        </div>

        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">Memories (this month)</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors">
            {profile?.usage?.commits_this_month ?? 0}
          </div>
        </div>

        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">Plan</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors capitalize">
            {profile?.plan || 'Free'}
          </div>
        </div>
      </div>

      {/* Quick Start */}
      <div className="bg-boswell-card rounded-2xl p-8 border border-boswell-border">
        <h2 className="font-display text-2xl text-white mb-6">Quick Start</h2>
        <ol className="space-y-5">
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ember-500 text-boswell-bg flex items-center justify-center text-sm font-semibold">1</span>
            <div>
              <p className="text-white font-medium">Install the extension</p>
              <p className="text-gray-500 text-sm mt-1">Download and install the .mcpb bundle for Claude Desktop, or use the CLI command for Claude Code.</p>
            </div>
          </li>
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ember-500 text-boswell-bg flex items-center justify-center text-sm font-semibold">2</span>
            <div>
              <p className="text-white font-medium">Start using Boswell</p>
              <p className="text-gray-500 text-sm mt-1">Open Claude and say <code className="px-2 py-0.5 bg-boswell-bg rounded text-ember-400">Call boswell_startup</code> to activate memory.</p>
            </div>
          </li>
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ember-500 text-boswell-bg flex items-center justify-center text-sm font-semibold">3</span>
            <div>
              <p className="text-white font-medium">Let Claude remember</p>
              <p className="text-gray-500 text-sm mt-1">Claude will automatically commit important context. Ask about previous conversations - it remembers!</p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  );
}
