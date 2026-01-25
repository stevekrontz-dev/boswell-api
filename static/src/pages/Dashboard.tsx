import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getCurrentUser, createCheckoutSession, fetchWithAuth, type UserProfile } from '../lib/api';

interface Insight {
  blob_hash: string;
  preview: string;
  link_count: number;
}

// Simplified narrative generator for insights
function narrateInsight(preview: string): string {
  if (!preview) return 'A memory worth revisiting';
  try {
    const data = JSON.parse(preview);
    const contentFields = ['achievement', 'title', 'decision', 'insight', 'principle', 'problem', 'action', 'summary', 'message', 'description', 'name', 'concept', 'vision'];
    // Check top-level content fields
    for (const field of contentFields) {
      if (data[field] && typeof data[field] === 'string' && data[field].length > 3) {
        return data[field].substring(0, 100);
      }
    }
    // Check inside payload object if present
    if (data.payload && typeof data.payload === 'object') {
      for (const field of contentFields) {
        if (data.payload[field] && typeof data.payload[field] === 'string' && data.payload[field].length > 3) {
          return data.payload[field].substring(0, 100);
        }
      }
    }
    // Check institution field specifically for scrape data
    if (data.institution && typeof data.institution === 'string') {
      return `${data.institution} data`;
    }
    // Fallback to first non-metadata string
    const metadataFields = ['type', 'date', 'timestamp', 'created_at', 'id', 'task_id', 'worker_id', 'branch', 'status', 'result', 'completed_at', 'layer', 'payload', 'slug', 'url', 'department', 'pages'];
    for (const [key, value] of Object.entries(data)) {
      if (!metadataFields.includes(key) && typeof value === 'string' && value.length > 3) {
        return (value as string).substring(0, 100);
      }
    }
  } catch { /* not JSON */ }
  return preview.replace(/[{}"]/g, '').substring(0, 100);
}

const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export default function Dashboard() {
  const { user: authUser } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  // Load insights when profile is ready and has subscription
  useEffect(() => {
    if (profile?.has_subscription && profile?.status === 'active') {
      loadInsights();
    }
  }, [profile]);

  const loadInsights = async () => {
    setInsightsLoading(true);
    try {
      const data = await fetchWithAuth('/v2/reflect?min_links=1&limit=5');
      setInsights(data.highly_connected || []);
    } catch (err) {
      console.error('Failed to load insights:', err);
    } finally {
      setInsightsLoading(false);
    }
  };

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
              {['50,000 memories per month', 'Unlimited branches', 'Semantic search', 'Priority support'].map((feature) => (
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

      {/* Insights Section - only for Pro users */}
      {profile?.has_subscription && profile?.status === 'active' && (
        <div className="card rounded-2xl p-6 reveal delay-3">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <h2 className="font-display text-xl text-parchment-50">Worth Remembering</h2>
                <p className="text-parchment-200/40 text-sm">Highly connected memories you might want to revisit</p>
              </div>
            </div>
            <Link to="/dashboard/mindstate" className="text-sm text-ember-500 hover:text-ember-400 transition-colors">
              View all →
            </Link>
          </div>

          {insightsLoading ? (
            <div className="text-center py-8 text-parchment-200/40">Loading insights...</div>
          ) : insights.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-parchment-200/40 mb-2">No insights yet</div>
              <p className="text-parchment-200/30 text-sm">As you build memories, connections will surface here.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {insights.map((insight) => (
                <Link
                  key={insight.blob_hash}
                  to={`/dashboard/mindstate?focus=${insight.blob_hash}`}
                  className="block p-4 rounded-xl bg-ink-900/50 border border-parchment-200/5 hover:border-purple-500/20 transition-all group"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-parchment-100 text-sm leading-relaxed truncate">
                        {narrateInsight(insight.preview)}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-parchment-200/40">
                        <span className="font-mono">{insight.blob_hash.substring(0, 8)}</span>
                        <span className="flex items-center gap-1">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                          </svg>
                          {insight.link_count} connections
                        </span>
                      </div>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-purple-500/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}

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
