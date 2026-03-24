import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAdminTenants, adminCreateTenant } from '../../lib/api';
import type { AdminTenant } from '../../lib/api';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

export default function AdminTenantsPage() {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState<AdminTenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create modal state
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getAdminTenants()
      .then(d => setTenants(d.tenants))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const result = await adminCreateTenant(newName.trim(), newEmail.trim() || undefined);
      setCreatedKey(result.api_key);
      // Refresh tenant list
      const updated = await getAdminTenants();
      setTenants(updated.tenants);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Failed to create tenant');
    } finally {
      setCreating(false);
    }
  };

  const closeModal = () => {
    setShowCreate(false);
    setNewName('');
    setNewEmail('');
    setCreatedKey(null);
    setCreateError(null);
    setCopied(false);
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">Tenants</h1>
        <div className="card p-6 animate-pulse">
          <div className="space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-10 bg-parchment-200/5 rounded" />)}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">Tenants</h1>
        <div className="card p-6 border-red-500/30">
          <p className="text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-2xl text-parchment-50">Tenants</h1>
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-parchment-200/10 text-parchment-200/60">
            {tenants.length}
          </span>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-ember-500 text-ink-950 hover:bg-ember-400 transition-colors"
        >
          + Create Tenant
        </button>
      </div>

      {/* Tenant Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-parchment-200/10">
                <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium">Name</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium">Created</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium">Commits</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium hidden md:table-cell">Storage</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium hidden md:table-cell">API (7d)</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-wider text-parchment-200/40 font-medium">Last Active</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((tenant) => {
                const lastActiveMs = tenant.last_active ? Date.now() - new Date(tenant.last_active).getTime() : Infinity;
                const isInactive = lastActiveMs > 30 * 24 * 60 * 60 * 1000;

                return (
                  <tr
                    key={tenant.id}
                    onClick={() => navigate(`/dashboard/admin/tenants/${tenant.id}`)}
                    className={`border-b border-parchment-200/5 cursor-pointer hover:bg-parchment-200/3 transition-colors ${
                      isInactive ? 'opacity-40' : ''
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="text-parchment-50 font-medium">{tenant.name}</div>
                      <div className="text-[10px] font-mono text-parchment-200/30 mt-0.5">{tenant.id.slice(0, 8)}</div>
                    </td>
                    <td className="px-4 py-3 text-parchment-200/50">
                      {tenant.created_at ? new Date(tenant.created_at).toLocaleDateString() : '--'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-parchment-200/70">{tenant.commit_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-parchment-200/50 hidden md:table-cell">{formatBytes(tenant.storage_bytes)}</td>
                    <td className="px-4 py-3 text-right font-mono text-parchment-200/50 hidden md:table-cell">{tenant.api_calls_7d.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-parchment-200/50">{timeAgo(tenant.last_active)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create Tenant Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-ink-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="card p-6 w-full max-w-md space-y-4">
            {createdKey ? (
              <>
                <h2 className="font-display text-xl text-parchment-50">Tenant Created</h2>
                <div className="p-4 rounded-lg bg-green-950/30 border border-green-500/20">
                  <p className="text-green-400 text-sm font-medium mb-2">Save this API key now -- it cannot be retrieved again!</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs font-mono text-parchment-50 bg-ink-950/50 p-2 rounded break-all">
                      {createdKey}
                    </code>
                    <button
                      onClick={() => { navigator.clipboard.writeText(createdKey); setCopied(true); }}
                      className="px-3 py-2 text-xs font-medium rounded bg-parchment-200/10 text-parchment-200/70 hover:bg-parchment-200/20 transition-colors flex-shrink-0"
                    >
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                </div>
                <button
                  onClick={closeModal}
                  className="w-full px-4 py-2 rounded-lg text-sm font-medium bg-parchment-200/10 text-parchment-200/70 hover:bg-parchment-200/20 transition-colors"
                >
                  Done
                </button>
              </>
            ) : (
              <>
                <h2 className="font-display text-xl text-parchment-50">Create Tenant</h2>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs uppercase tracking-wider text-parchment-200/40 mb-1">Name *</label>
                    <input
                      type="text"
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      placeholder="Tenant name"
                      className="w-full px-3 py-2 rounded-lg bg-ink-900/50 border border-parchment-200/10 text-parchment-50 text-sm placeholder:text-parchment-200/20 focus:outline-none focus:border-ember-500/50"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-xs uppercase tracking-wider text-parchment-200/40 mb-1">Email (optional)</label>
                    <input
                      type="email"
                      value={newEmail}
                      onChange={e => setNewEmail(e.target.value)}
                      placeholder="contact@example.com"
                      className="w-full px-3 py-2 rounded-lg bg-ink-900/50 border border-parchment-200/10 text-parchment-50 text-sm placeholder:text-parchment-200/20 focus:outline-none focus:border-ember-500/50"
                    />
                  </div>
                </div>
                {createError && (
                  <p className="text-red-400 text-sm">{createError}</p>
                )}
                <div className="flex gap-3">
                  <button
                    onClick={closeModal}
                    className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-parchment-200/10 text-parchment-200/70 hover:bg-parchment-200/20 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={creating || !newName.trim()}
                    className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-ember-500 text-ink-950 hover:bg-ember-400 transition-colors disabled:opacity-50"
                  >
                    {creating ? 'Creating...' : 'Create'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
