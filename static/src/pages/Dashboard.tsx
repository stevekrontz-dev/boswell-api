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
      <div className="space-y-8 animate-fade-in">
        <div className="text-center md:text-left">
          <h1 className="font-display text-3xl md:text-4xl text-parchment-50 mb-2">
            Complete Your Setup
          </h1>
          <p className="text-parchment-200/60 font-body">
            Subscribe to Boswell Pro to get started with your AI memory.
          </p>
        </div>
