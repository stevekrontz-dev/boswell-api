import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getAdminTenantDetail, adminCreateBranches } from '../../lib/api';
import type { AdminTenantDetail } from '../../lib/api';

export default function AdminTenantDetailPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const [data, setData] = useState<AdminTenantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Branch creation
  const [newBranch, setNewBranch] = useState('');
  const [creatingBranch, setCreatingBranch] = useState(false);

  const fetchData = () => {
    if (!tenantId) return;
    getAdminTenantDetail(tenantId)
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [tenantId]);

  const handleCreateBranch = async () => {
    if (!newBranch.trim() || !tenantId) return;
    setCreatingBranch(true);
    try {
      await adminCreateBranches(tenantId, [newBranch.trim().toLowerCase()]);
      setNewBranch('');
      fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create branch');
    } finally {
      setCreatingBranch(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Link to="/dashboard/admin/tenants" className="text-sm text-parchment-200/40 hover:text-parchment-200/70 transition-colors">
          &larr; Back to Tenants
        </Link>
        <div className="card p-6 animate-pulse">
          <div className="h-8 bg-parchment-200/5 rounded w-48 mb-4" />
          <div className="h-4 bg-parchment-200/5 rounded w-64" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <Link to="/dashboard/admin/tenants" className="text-sm text-parchment-200/40 hover:text-parchment-200/70 transition-colors">
          &larr; Back to Tenants
        </Link>
        <div className="card p-6 border-red-500/30">
          <p className="text-red-400">{error || 'Tenant not found'}</p>
        </div>
      </div>
    );
  }

  const maxCommits = Math.max(...data.charts.commits_by_branch.map(d => d.commits), 1);
  const maxRequests = Math.max(...(data.charts.api_calls_by_day.map(d => d.requests) || [1]), 1);
  const totalCommits = data.charts.commits_by_branch.reduce((sum, d) => sum + d.commits, 0);

  return (
    <div className="space-y-6">
      {/* Back Link */}
      <Link to="/dashboard/admin/tenants" className="text-sm text-parchment-200/40 hover:text-parchment-200/70 transition-colors">
        &larr; Back to Tenants
      </Link>

      {/* Tenant Info */}
      <div className="card p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-display text-2xl text-parchment-50">{data.tenant.name}</h1>
            <div className="flex flex-wrap gap-4 mt-3 text-sm">
              <div>
                <span className="text-parchment-200/40">ID: </span>
                <span className="font-mono text-parchment-200/60">{data.tenant.id}</span>
              </div>
              <div>
                <span className="text-parchment-200/40">Created: </span>
                <span className="text-parchment-200/60">
                  {data.tenant.created_at ? new Date(data.tenant.created_at).toLocaleDateString() : '--'}
                </span>
              </div>
              <div>
                <span className="text-parchment-200/40">Total Commits: </span>
                <span className="text-parchment-200/60">{totalCommits.toLocaleString()}</span>
              </div>
            </div>
          </div>
          {data.user && (
            <div className="text-right">
              <div className="text-sm text-parchment-200/60">{data.user.email}</div>
              <div className="flex items-center gap-2 mt-1 justify-end">
                <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-medium ${
                  data.user.plan === 'pro' ? 'bg-ember-500/20 text-ember-400' : 'bg-parchment-200/10 text-parchment-200/50'
                }`}>
                  {data.user.plan}
                </span>
                {data.user.status && (
                  <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-medium ${
                    data.user.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'
                  }`}>
                    {data.user.status}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Branches */}
      <div className="card p-6">
        <h3 className="text-sm font-medium text-parchment-200/60 mb-3">Branches</h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {(data.branches || []).map(b => (
            <span key={b} className="px-3 py-1 rounded-full text-xs font-mono bg-ink-900/50 border border-parchment-200/10 text-parchment-200/60">
              {b}
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newBranch}
            onChange={e => setNewBranch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreateBranch()}
            placeholder="New branch name"
            className="flex-1 px-3 py-1.5 rounded-lg bg-ink-900/50 border border-parchment-200/10 text-parchment-50 text-sm placeholder:text-parchment-200/20 focus:outline-none focus:border-ember-500/50"
          />
          <button
            onClick={handleCreateBranch}
            disabled={creatingBranch || !newBranch.trim()}
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-ember-500 text-ink-950 hover:bg-ember-400 transition-colors disabled:opacity-50"
          >
            {creatingBranch ? '...' : 'Add'}
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Commits by Branch */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">Commits by Branch</h3>
          {data.charts.commits_by_branch.length > 0 ? (
            <div className="space-y-2">
              {data.charts.commits_by_branch.map((d) => (
                <div key={d.branch} className="flex items-center gap-3">
                  <span className="text-xs font-mono text-parchment-200/50 w-32 truncate flex-shrink-0" title={d.branch}>
                    {d.branch}
                  </span>
                  <div className="flex-1 h-5 bg-ink-900/50 rounded overflow-hidden">
                    <div
                      className="h-full bg-ember-500/60 rounded"
                      style={{ width: `${(d.commits / maxCommits) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-parchment-200/40 w-12 text-right flex-shrink-0">
                    {d.commits}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-parchment-200/30 text-sm">No branches</div>
          )}
        </div>

        {/* API Calls Timeline */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">API Calls (30d)</h3>
          {data.charts.api_calls_by_day.length > 0 ? (
            <div className="flex items-end gap-px h-32">
              {data.charts.api_calls_by_day.map((d, i) => (
                <div
                  key={i}
                  className="flex-1 bg-ember-500/50 rounded-t hover:bg-ember-500/80 transition-colors"
                  style={{ height: `${(d.requests / maxRequests) * 100}%`, minHeight: '1px' }}
                  title={`${d.day}: ${d.requests} requests`}
                />
              ))}
            </div>
          ) : (
            <div className="h-32 flex items-center justify-center text-parchment-200/30 text-sm">No API data</div>
          )}
        </div>
      </div>

      {/* Top Actions */}
      <div className="card p-6">
        <h3 className="text-sm font-medium text-parchment-200/60 mb-4">Top Actions (7d)</h3>
        {data.charts.top_actions.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {data.charts.top_actions.map((d) => (
              <div
                key={d.action}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-ink-900/50 border border-parchment-200/10"
              >
                <span className="text-xs text-parchment-200/60">{d.action}</span>
                <span className="text-xs font-mono text-parchment-200/40">{d.count}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-parchment-200/30 text-sm">No actions recorded</div>
        )}
      </div>
    </div>
  );
}
