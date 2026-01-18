import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import {
  isWebAuthnSupported,
  registerPasskey,
  setPasskeyRegistered,
  listPasskeys,
  type PasskeyCredential,
} from '../lib/webauthn';

export default function Security() {
  const { user, token } = useAuth();
  const [passkeys, setPasskeys] = useState<PasskeyCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [webAuthnSupported, setWebAuthnSupported] = useState(false);
  const [friendlyName, setFriendlyName] = useState('');

  useEffect(() => {
    setWebAuthnSupported(isWebAuthnSupported());
    loadPasskeys();
  }, [token]);

  const loadPasskeys = async () => {
    if (!token) return;
    setLoading(true);
    const keys = await listPasskeys(token);
    setPasskeys(keys);
    setLoading(false);
  };

  const handleRegisterPasskey = async () => {
    if (!user) return;
    
    setError('');
    setSuccess('');
    setRegistering(true);

    const name = friendlyName.trim() || getDeviceName();
    const result = await registerPasskey(user.email, name);
    
    setRegistering(false);

    if (result.success) {
      setSuccess('Passkey registered successfully! You can now sign in with Face ID or Touch ID.');
      setFriendlyName('');
      setPasskeyRegistered(true);
      loadPasskeys();
    } else {
      setError(result.error || 'Failed to register passkey');
    }
  };

  const getDeviceName = (): string => {
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return 'iPhone';
    if (/iPad/.test(ua)) return 'iPad';
    if (/Mac/.test(ua)) return 'Mac';
    if (/Android/.test(ua)) return 'Android';
    if (/Windows/.test(ua)) return 'Windows PC';
    return 'My Device';
  };

  return (
    <div className="max-w-2xl">
      <h1 className="font-display text-2xl text-parchment-50 mb-2">Security</h1>
      <p className="text-parchment-200/50 mb-8">
        Manage your account security and authentication methods.
      </p>

      {/* Passkeys Section */}
      <div className="bg-ink-900/30 border border-parchment-200/10 rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-blue-500/10 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
              <rect x="3" y="3" width="18" height="18" rx="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg text-parchment-50">Face ID & Passkeys</h2>
            <p className="text-parchment-200/40 text-sm">
              Sign in faster with biometric authentication
            </p>
          </div>
        </div>

        {!webAuthnSupported ? (
          <div className="bg-amber-950/30 border border-amber-900/30 rounded-xl p-4 text-amber-400 text-sm">
            Your browser doesn't support passkeys. Try Safari on iOS/macOS or Chrome on Android.
          </div>
        ) : (
          <>
            {error && (
              <div className="mb-4 p-4 bg-red-950/50 border border-red-900/30 rounded-xl text-red-400 text-sm">
                {error}
              </div>
            )}

            {success && (
              <div className="mb-4 p-4 bg-green-950/50 border border-green-900/30 rounded-xl text-green-400 text-sm">
                {success}
              </div>
            )}

            {/* Registered Passkeys */}
            {loading ? (
              <div className="text-parchment-200/40 text-sm py-4">Loading passkeys...</div>
            ) : passkeys.length > 0 ? (
              <div className="space-y-3 mb-6">
                <h3 className="text-parchment-200/60 text-sm font-medium">Registered Passkeys</h3>
                {passkeys.map((pk) => (
                  <div
                    key={pk.id}
                    className="flex items-center justify-between bg-ink-950/50 border border-parchment-200/5 rounded-xl p-4"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-parchment-200/5 rounded-lg flex items-center justify-center">
                        <svg className="w-4 h-4 text-parchment-200/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" />
                        </svg>
                      </div>
                      <div>
                        <div className="text-parchment-50 text-sm">{pk.friendly_name}</div>
                        <div className="text-parchment-200/30 text-xs">
                          {pk.device_type} • Added {new Date(pk.created_at).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                    {pk.last_used_at && (
                      <div className="text-parchment-200/30 text-xs">
                        Last used {new Date(pk.last_used_at).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-ink-950/50 border border-parchment-200/5 rounded-xl p-6 mb-6 text-center">
                <div className="w-12 h-12 bg-parchment-200/5 rounded-full flex items-center justify-center mx-auto mb-3">
                  <svg className="w-6 h-6 text-parchment-200/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" />
                  </svg>
                </div>
                <p className="text-parchment-200/50 text-sm">
                  No passkeys registered yet. Add one to sign in with Face ID or Touch ID.
                </p>
              </div>
            )}

            {/* Register New Passkey */}
            <div className="border-t border-parchment-200/10 pt-6">
              <h3 className="text-parchment-200/60 text-sm font-medium mb-3">Add a New Passkey</h3>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={friendlyName}
                  onChange={(e) => setFriendlyName(e.target.value)}
                  placeholder={`Device name (e.g., "${getDeviceName()}")`}
                  className="flex-1 bg-ink-950/50 border border-parchment-200/10 rounded-xl px-4 py-2.5 text-parchment-50 text-sm placeholder-parchment-200/30 focus:border-ember-500/50 transition-colors"
                />
                <button
                  onClick={handleRegisterPasskey}
                  disabled={registering}
                  className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium rounded-xl transition-colors disabled:cursor-not-allowed inline-flex items-center gap-2"
                >
                  {registering ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Registering...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      <span>Add Passkey</span>
                    </>
                  )}
                </button>
              </div>
              <p className="text-parchment-200/30 text-xs mt-2">
                This will prompt for Face ID, Touch ID, or your device PIN.
              </p>
            </div>
          </>
        )}
      </div>

      {/* Password Section */}
      <div className="bg-ink-900/30 border border-parchment-200/10 rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-parchment-200/5 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-parchment-200/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg text-parchment-50">Password</h2>
            <p className="text-parchment-200/40 text-sm">
              Change your password or enable two-factor authentication
            </p>
          </div>
        </div>

        <button className="text-ember-500 hover:text-ember-400 text-sm font-medium transition-colors">
          Change password →
        </button>
      </div>
    </div>
  );
}
