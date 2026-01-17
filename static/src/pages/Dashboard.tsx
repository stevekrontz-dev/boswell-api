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
        <div className="text-parchment-200/50">Loading...</div>
      </div>
    );
  }

  // Show upgrade prompt if pending payment
  if (profile?.status === 'pending_payment') {
    return (
      <div className="space-y-10 animate-fade-in">
        <div className="text-center">
          <h1 className="font-display text-4xl md:text-5xl text-parchment-50 mb-4">
            Complete Your Setup
          </h1>
          <p className="text-parchment-200/60 text-lg max-w-xl mx-auto">
            Subscribe to Boswell Pro to get started with your AI memory.
          </p>
        </div>

        <div className="card rounded-2xl p-8 max-w-xl mx-auto">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full bg-ember-500/10 border border-ember-500/20 flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
            <h2 className="font-display text-2xl text-parchment-50 mb-2">Boswell Pro</h2>
            <p className="text-parchment-200/50 mb-8">
              Unlimited memory for your Claude instances.
            </p>
            
            <div className="space-y-3 text-left mb-8">
              {['50,000 memories per month', 'Unlimited branches', '5GB encrypted storage', 'Priority support'].map((feature) => (
                <div key={feature} className="flex items-center gap-3 text-parchment-200/70">
                  <svg className="w-5 h-5 text-ember-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>{feature}</span>
                </div>
              ))}
            </div>
            
            <div className="text-4xl font-display text-parchment-50 mb-6">
              $19<span className="text-lg text-parchment-200/40">/month</span>
            </div>
            
            <button
              onClick={handleCheckout}
              disabled={checkoutLoading}
              className="w-full px-6 py-3 bg-ember-500 hover:bg-ember-400 disabled:opacity-50 text-ink-950 font-medium rounded-full transition-colors"
            >
              {checkoutLoading ? 'Redirecting...' : 'Subscribe to Pro'}
            </button>
          </div>
        </div>
      </div>
    );
  }


  return (
    <div className="space-y-10">
      {/* Welcome Header */}
      <div className="text-center md:text-left reveal">
        <h1 className="font-display text-4xl md:text-5xl text-parchment-50 mb-3">
          Welcome back, <span className="text-ember-500 italic">{profile?.name || authUser?.name || 'there'}</span>
        </h1>
        <p className="text-parchment-200/60 text-lg">
          Your Boswell memory is ready to use.
        </p>
      </div>

      {/* Install Section */}
      <div className="card rounded-2xl p-6 reveal delay-1">
        <h2 className="font-display text-xl text-parchment-50 mb-4">Install Boswell</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {downloadUrl && (
            <a
              href={downloadUrl}
              className="flex items-center gap-4 p-4 rounded-xl border border-parchment-200/10 hover:border-ember-500/30 bg-ink-900/50 transition-all group"
            >
              <div className="w-12 h-12 rounded-full bg-ember-500/10 border border-ember-500/20 flex items-center justify-center group-hover:bg-ember-500/20 transition-colors">
                <svg className="w-6 h-6 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </div>
              <div>
                <div className="font-medium text-parchment-50">Claude Desktop</div>
                <div className="text-sm text-parchment-200/50">Download .mcpb bundle</div>
              </div>
            </a>
          )}
          <a
            href="/dashboard/connect"
            className="flex items-center gap-4 p-4 rounded-xl border border-parchment-200/10 hover:border-ember-500/30 bg-ink-900/50 transition-all group"
          >
            <div className="w-12 h-12 rounded-full bg-ember-500/10 border border-ember-500/20 flex items-center justify-center group-hover:bg-ember-500/20 transition-colors">
              <svg className="w-6 h-6 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
            <div>
              <div className="font-medium text-parchment-50">Other Methods</div>
              <div className="text-sm text-parchment-200/50">Claude Code, Claude.ai</div>
            </div>
          </a>
        </div>
      </div>


      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 reveal delay-2">
        <div className="card rounded-2xl p-6 group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-parchment-200/50 text-sm uppercase tracking-wider">Branches</span>
            <div className="w-8 h-8 rounded-full bg-ember-500/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display text-parchment-50 group-hover:text-ember-500 transition-colors">
            {profile?.usage?.branches ?? 0}
          </div>
        </div>

        <div className="card rounded-2xl p-6 group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-parchment-200/50 text-sm uppercase tracking-wider">Memories</span>
            <div className="w-8 h-8 rounded-full bg-ember-500/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display text-parchment-50 group-hover:text-ember-500 transition-colors">
            {profile?.usage?.commits_this_month ?? 0}
          </div>
        </div>

        <div className="card rounded-2xl p-6 group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-parchment-200/50 text-sm uppercase tracking-wider">Plan</span>
            <div className="w-8 h-8 rounded-full bg-ember-500/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display text-parchment-50 group-hover:text-ember-500 transition-colors capitalize">
            {profile?.plan || 'Free'}
          </div>
        </div>
      </div>


      {/* Quick Start */}
      <div className="card rounded-2xl p-8 reveal delay-3">
        <h2 className="font-display text-2xl text-parchment-50 mb-8">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { step: '1', title: 'Install', desc: 'Download the bundle or use the CLI command for Claude Code.' },
            { step: '2', title: 'Connect', desc: 'Say "Call boswell_startup" to activate memory.' },
            { step: '3', title: 'Remember', desc: 'Claude commits context automatically. Just ask.' },
          ].map((item) => (
            <div key={item.step} className="text-center">
              <div className="w-10 h-10 rounded-full bg-ember-500 text-ink-950 flex items-center justify-center mx-auto mb-4 font-display text-lg">
                {item.step}
              </div>
              <h3 className="font-display text-lg text-parchment-50 mb-2">{item.title}</h3>
              <p className="text-parchment-200/50 text-sm">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* API Key Section - only if they have one */}
      {profile?.api_key && (
        <div className="card rounded-2xl p-6 reveal delay-4">
          <h2 className="font-display text-xl text-parchment-50 mb-4">Your API Key</h2>
          <div className="flex items-center gap-3">
            <code className="flex-1 bg-ink-950 px-4 py-3 rounded-lg text-sm text-ember-500 font-mono break-all border border-parchment-200/10">
              {profile.api_key}
            </code>
            <button
              onClick={copyApiKey}
              className="px-4 py-3 bg-ink-800 hover:bg-ink-700 rounded-lg text-sm text-parchment-100 transition-colors"
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <p className="text-parchment-200/40 text-sm mt-3">
            Keep this key safe. You'll need it to connect your Claude instances.
          </p>
        </div>
      )}
    </div>
  );
}
