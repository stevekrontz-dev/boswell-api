/**
 * WebAuthn/Passkey utilities for Face ID and Touch ID authentication
 */

import {
  startRegistration,
  startAuthentication,
  browserSupportsWebAuthn,
} from '@simplewebauthn/browser';

const API_BASE = '';

export interface PasskeyCredential {
  id: string;
  friendly_name: string;
  device_type: string;
  created_at: string;
  last_used_at: string | null;
}

/**
 * Check if the browser supports WebAuthn/Passkeys
 */
export function isWebAuthnSupported(): boolean {
  return browserSupportsWebAuthn();
}

/**
 * Check if we have a registered passkey for this user (stored in localStorage)
 */
export function hasStoredPasskey(): boolean {
  return localStorage.getItem('boswell_passkey_registered') === 'true';
}

/**
 * Mark that we've registered a passkey
 */
export function setPasskeyRegistered(registered: boolean): void {
  if (registered) {
    localStorage.setItem('boswell_passkey_registered', 'true');
  } else {
    localStorage.removeItem('boswell_passkey_registered');
  }
}

/**
 * Register a new passkey for the user
 */
export async function registerPasskey(
  userId: string,
  friendlyName: string = 'My Device'
): Promise<{ success: boolean; error?: string }> {
  try {
    // Get registration options from server
    const optionsRes = await fetch(`${API_BASE}/auth/register/options`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });

    if (!optionsRes.ok) {
      const err = await optionsRes.json();
      return { success: false, error: err.error || 'Failed to get registration options' };
    }

    const options = await optionsRes.json();

    // Start the WebAuthn registration ceremony (triggers Face ID/Touch ID)
    const credential = await startRegistration(options);

    // Verify with server
    const verifyRes = await fetch(`${API_BASE}/auth/register/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        credential,
        friendly_name: friendlyName,
      }),
    });

    if (!verifyRes.ok) {
      const err = await verifyRes.json();
      return { success: false, error: err.error || 'Registration verification failed' };
    }

    // Mark passkey as registered
    setPasskeyRegistered(true);

    return { success: true };
  } catch (error: any) {
    // User cancelled or other WebAuthn error
    if (error.name === 'NotAllowedError') {
      return { success: false, error: 'Authentication was cancelled' };
    }
    return { success: false, error: error.message || 'Registration failed' };
  }
}

/**
 * Authenticate with a passkey (Face ID/Touch ID)
 */
export async function authenticateWithPasskey(
  userId: string
): Promise<{ success: boolean; token?: string; error?: string }> {
  try {
    // Get authentication options from server
    const optionsRes = await fetch(`${API_BASE}/auth/login/options`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });

    if (!optionsRes.ok) {
      const err = await optionsRes.json();
      return { success: false, error: err.error || 'Failed to get login options' };
    }

    const options = await optionsRes.json();

    // Start the WebAuthn authentication ceremony (triggers Face ID/Touch ID)
    const credential = await startAuthentication(options);

    // Verify with server
    const verifyRes = await fetch(`${API_BASE}/auth/login/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        credential,
      }),
      credentials: 'include', // Include cookies
    });

    if (!verifyRes.ok) {
      const err = await verifyRes.json();
      return { success: false, error: err.error || 'Authentication failed' };
    }

    const result = await verifyRes.json();
    return { success: true, token: result.token };
  } catch (error: any) {
    // User cancelled or other WebAuthn error
    if (error.name === 'NotAllowedError') {
      return { success: false, error: 'Authentication was cancelled' };
    }
    return { success: false, error: error.message || 'Authentication failed' };
  }
}

/**
 * List registered passkeys for the current user
 */
export async function listPasskeys(token: string): Promise<PasskeyCredential[]> {
  try {
    const res = await fetch(`${API_BASE}/auth/passkeys`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.passkeys || [];
  } catch {
    return [];
  }
}
