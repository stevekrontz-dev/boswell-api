import { useState, useEffect } from 'react';
import { getCurrentUser, createCheckoutSession, type UserProfile } from '../lib/api';

export default function Billing() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
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

  const handleUpgrade = async () => {
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

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-parchment-200/50">Loading...</div>
      </div>
    );
  }

  const isPro = profile?.plan === 'pro' || profile?.status === 'active';
  const branchUsage = profile?.usage?.branches ?? 0;
  const commitUsage = profile?.usage?.commits_this_month ?? 0;
  const branchLimit = isPro ? 'Unlimited' : 6;
  const commitLimit = isPro ? 50000 : 100;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-parchment-50">Billing</h1>
        <p className="text-parchment-200/60 mt-1">Manage your subscription and usage.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card rounded-xl p-6">
          <h3 className="text-lg font-semibold text-parchment-50 mb-4">Current Plan</h3>
          <div className="flex items-baseline gap-2 mb-4">
            <span className="text-3xl font-bold text-parchment-50">{isPro ? 'Pro' : 'Free'}</span>
            <span className="text-parchment-200/60">{isPro ? '$29/month' : '$0/month'}</span>
          </div>
          <ul className="space-y-2 text-parchment-200/60 text-sm mb-6">
            {isPro ? (
              <>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Unlimited branches
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  50,000 memories per month
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  5GB encrypted storage
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Priority support
                </li>
              </>
            ) : (
              <>
                <li>6 branches</li>
                <li>100 memories</li>
                <li>Basic support</li>
              </>
            )}
          </ul>
          {!isPro && (
            <button
              onClick={handleUpgrade}
              disabled={checkoutLoading}
              className="w-full py-2 bg-ember-500 hover:bg-ember-400 disabled:bg-ink-700 text-ink-950 font-medium rounded-lg transition-colors"
            >
              {checkoutLoading ? 'Loading...' : 'Upgrade to Pro'}
            </button>
          )}
          {isPro && (
            <div className="text-center py-2 text-parchment-200/60 text-sm">
              You're on the Pro plan
            </div>
          )}
        </div>

        <div className="card rounded-xl p-6">
          <h3 className="text-lg font-semibold text-parchment-50 mb-4">Usage This Month</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-parchment-200/60">Branches</span>
                <span className="text-parchment-100">{branchUsage} / {branchLimit}</span>
              </div>
              <div className="h-2 bg-ink-800 rounded-full">
                <div
                  className="h-2 bg-ember-500 rounded-full transition-all"
                  style={{ width: isPro ? '0%' : `${Math.min((branchUsage / 6) * 100, 100)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-parchment-200/60">Memories</span>
                <span className="text-parchment-100">{commitUsage} / {commitLimit.toLocaleString()}</span>
              </div>
              <div className="h-2 bg-ink-800 rounded-full">
                <div
                  className="h-2 bg-ember-500 rounded-full transition-all"
                  style={{ width: `${Math.min((commitUsage / commitLimit) * 100, 100)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-parchment-200/60">API Calls</span>
                <span className="text-parchment-100">0 / {isPro ? '100,000' : '1,000'}</span>
              </div>
              <div className="h-2 bg-ink-800 rounded-full">
                <div className="h-2 bg-ember-500 rounded-full w-0" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
