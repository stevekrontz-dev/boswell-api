const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

export async function register(email: string, password: string, name: string, agreedToTerms: boolean = false) {
  const res = await fetch(`${API_BASE}/v2/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name, agreed_to_terms: agreedToTerms })
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
  if (res.status === 401) {
    localStorage.removeItem('boswell_token');
    localStorage.removeItem('boswell_user');
    window.location.href = '/dashboard/login';
    throw new Error('Session expired');
  }
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

export interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  tenant_id: string | null;
  plan: string;
  status: 'pending_payment' | 'active' | 'suspended';
  api_key: string | null;
  has_subscription: boolean;
  member_since: string | null;
  is_admin: boolean;
  usage: {
    branches: number;
    commits_this_month: number;
  } | null;
}

export async function getCurrentUser(tokenOverride?: string): Promise<UserProfile> {
  const token = tokenOverride || localStorage.getItem('boswell_token');
  const res = await fetch(`${API_BASE}/v2/me`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
    },
  });
  if (res.status === 401 && !tokenOverride) {
    localStorage.removeItem('boswell_token');
    localStorage.removeItem('boswell_user');
    window.location.href = '/dashboard/login';
    throw new Error('Session expired');
  }
  return res.json();
}

export async function createCheckoutSession(planId: string = 'pro') {
  return fetchWithAuth('/v2/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId })
  });
}

export interface Branch {
  name: string;
  head_commit: string | null;
  created_at: string;
  commits: number;
  last_activity: string;
}

export async function getBranches(): Promise<{ branches: Branch[]; count: number }> {
  return fetchWithAuth('/v2/branches');
}

export async function createBranch(name: string, fromBranch: string = 'command-center'): Promise<Branch> {
  return fetchWithAuth('/v2/branch', {
    method: 'POST',
    body: JSON.stringify({ name, from: fromBranch })
  });
}

export async function deleteBranch(name: string): Promise<{ status: string; branch: string }> {
  return fetchWithAuth(`/v2/branch/${encodeURIComponent(name)}`, {
    method: 'DELETE'
  });
}

// Admin types
export interface AdminPulse {
  cards: {
    total_tenants: number;
    total_commits: number;
    total_blobs: number;
    api_calls_24h: number;
    total_storage_bytes: number;
  };
  charts: {
    request_volume: { day: string; requests: number }[];
    error_rates: { day: string; error_rate: number; errors: number }[];
    response_times: { p50: number; p95: number; p99: number; avg: number };
  };
  status: {
    system_health: 'healthy' | 'degraded';
    recent_500_errors: number;
    storage_bytes: number;
    encryption: string;
    audit: string;
  };
  timestamp: string;
}

export interface AdminTenant {
  id: string;
  name: string;
  created_at: string | null;
  commit_count: number;
  blob_count: number;
  storage_bytes: number;
  api_calls_7d: number;
  last_active: string | null;
}

export interface AdminTenantDetail {
  tenant: { id: string; name: string; created_at: string | null };
  user: { email: string | null; plan: string; status: string | null } | null;
  branches: string[];
  charts: {
    commits_by_branch: { branch: string; commits: number }[];
    api_calls_by_day: { day: string; requests: number }[];
    top_actions: { action: string; count: number }[];
  };
}

export interface AdminAlert {
  severity: 'critical' | 'warning' | 'info';
  type: string;
  message: string;
  details: Record<string, unknown>;
}

export interface AdminAlertsResponse {
  alerts: AdminAlert[];
  count: number;
  critical_count: number;
  warning_count: number;
  timestamp: string;
}

// Admin API functions
export async function getAdminPulse(): Promise<AdminPulse> {
  return fetchWithAuth('/v2/admin/pulse');
}

export async function getAdminTenants(): Promise<{ tenants: AdminTenant[]; count: number }> {
  return fetchWithAuth('/v2/admin/tenants');
}

export async function getAdminTenantDetail(tenantId: string): Promise<AdminTenantDetail> {
  return fetchWithAuth(`/v2/admin/tenants/${tenantId}`);
}

export async function getAdminAlerts(): Promise<AdminAlertsResponse> {
  return fetchWithAuth('/v2/admin/alerts');
}

export async function adminCreateTenant(name: string, email?: string, branches?: string[]): Promise<{ tenant_id: string; api_key: string; name: string; branches: string[] }> {
  return fetchWithAuth('/v2/admin/create-tenant', {
    method: 'POST',
    body: JSON.stringify({ name, email, branches }),
  });
}

export async function adminCreateBranches(tenantId: string, names: string[]): Promise<{ created: string[]; count: number }> {
  return fetchWithAuth(`/v2/admin/tenants/${tenantId}/branches`, {
    method: 'POST',
    body: JSON.stringify({ names }),
  });
}
