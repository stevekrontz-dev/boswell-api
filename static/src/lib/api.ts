const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export async function register(email: string, password: string, name: string) {
  const res = await fetch(`${API_BASE}/v2/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name })
  });
  const data = await res.json();

  if (data.token && data.user_id) {
    return {
      token: data.token,
      user: {
        id: data.user_id,
        email: data.email,
        name: data.name
      }
    };
  }
  return data;
}

export async function login(email: string, password: string) {
  const res = await fetch(`${API_BASE}/v2/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  return res.json();
}

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem('boswell_token');
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    },
  });
  return res.json();
}

export async function getApiKeys() {
  const data = await fetchWithAuth('/v2/auth/keys');
  if (Array.isArray(data)) { return { keys: data }; }
  return data;
}


export async function createApiKey() {
  return fetchWithAuth('/v2/auth/keys/create', { method: 'POST' });
}

export async function deleteApiKey(keyId: string) {
  return fetchWithAuth('/v2/auth/keys/' + keyId, { method: 'DELETE' });
}
