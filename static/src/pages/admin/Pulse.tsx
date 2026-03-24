import { useState, useEffect } from 'react';
import { getAdminPulse } from '../../lib/api';
import type { AdminPulse } from '../../lib/api';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatNumber(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toLocaleString();
}

export default function AdminPulsePage() {
  const [data, setData] = useState<AdminPulse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    getAdminPulse()
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">System Pulse</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-8 bg-parchment-200/5 rounded w-16 mb-2" />
              <div className="h-4 bg-parchment-200/5 rounded w-24" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">System Pulse</h1>
        <div className="card p-6 border-red-500/30">
          <p className="text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const maxRequests = Math.max(...data.charts.request_volume.map(d => d.requests), 1);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl text-parchment-50">System Pulse</h1>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
            data.status.system_health === 'healthy'
              ? 'bg-green-950/50 text-green-400 border border-green-500/20'
              : 'bg-red-950/50 text-red-400 border border-red-500/20'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              data.status.system_health === 'healthy' ? 'bg-green-400' : 'bg-red-400'
            }`} />
            {data.status.system_health === 'healthy' ? 'Healthy' : 'Degraded'}
          </span>
          <span className="text-parchment-200/30 text-xs">
            {new Date(data.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-6">
          <div className="font-display text-3xl text-parchment-50">{data.cards.total_tenants}</div>
          <div className="text-xs uppercase tracking-wider text-parchment-200/40 mt-1">Tenants</div>
        </div>
        <div className="card p-6">
          <div className="font-display text-3xl text-parchment-50">{formatNumber(data.cards.total_commits)}</div>
          <div className="text-xs uppercase tracking-wider text-parchment-200/40 mt-1">Total Commits</div>
        </div>
        <div className="card p-6">
          <div className="font-display text-3xl text-parchment-50">{formatBytes(data.cards.total_storage_bytes)}</div>
          <div className="text-xs uppercase tracking-wider text-parchment-200/40 mt-1">Storage</div>
        </div>
        <div className="card p-6">
          <div className="font-display text-3xl text-parchment-50">{formatNumber(data.cards.api_calls_24h)}</div>
          <div className="text-xs uppercase tracking-wider text-parchment-200/40 mt-1">API Calls (24h)</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Request Volume */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">Request Volume (7d)</h3>
          {data.charts.request_volume.length > 0 ? (
            <div className="flex items-end gap-1 h-32">
              {data.charts.request_volume.map((d, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full bg-ember-500/70 rounded-t hover:bg-ember-500 transition-colors"
                    style={{ height: `${(d.requests / maxRequests) * 100}%`, minHeight: '2px' }}
                    title={`${d.day}: ${d.requests} requests`}
                  />
                  <span className="text-[10px] text-parchment-200/30">
                    {new Date(d.day).toLocaleDateString('en', { weekday: 'short' })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-32 flex items-center justify-center text-parchment-200/30 text-sm">No data</div>
          )}
        </div>

        {/* Error Rates */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">Error Rate (7d)</h3>
          {data.charts.error_rates.length > 0 ? (
            <div className="flex items-end gap-1 h-32">
              {data.charts.error_rates.map((d, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className={`w-full rounded-t transition-colors ${
                      d.error_rate > 5 ? 'bg-red-500/70 hover:bg-red-500' : 'bg-green-500/40 hover:bg-green-500/60'
                    }`}
                    style={{ height: `${Math.max(d.error_rate * 2, 2)}%`, minHeight: '2px' }}
                    title={`${d.day}: ${d.error_rate}% (${d.errors} errors)`}
                  />
                  <span className="text-[10px] text-parchment-200/30">
                    {new Date(d.day).toLocaleDateString('en', { weekday: 'short' })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-32 flex items-center justify-center text-parchment-200/30 text-sm">No data</div>
          )}
        </div>
      </div>

      {/* Response Times + System Info */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">Response Times (24h)</h3>
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'p50', value: data.charts.response_times.p50 },
              { label: 'p95', value: data.charts.response_times.p95 },
              { label: 'p99', value: data.charts.response_times.p99 },
              { label: 'avg', value: data.charts.response_times.avg },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <div className={`font-mono text-lg ${
                  value > 1000 ? 'text-red-400' : value > 500 ? 'text-amber-400' : 'text-parchment-50'
                }`}>
                  {value < 1000 ? `${Math.round(value)}ms` : `${(value / 1000).toFixed(1)}s`}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-parchment-200/40 mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-sm font-medium text-parchment-200/60 mb-4">System Info</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-parchment-200/40">Encryption</span>
              <span className={data.status.encryption === 'enabled' ? 'text-green-400' : 'text-red-400'}>
                {data.status.encryption}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-200/40">Audit Logging</span>
              <span className={data.status.audit === 'enabled' ? 'text-green-400' : 'text-red-400'}>
                {data.status.audit}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-200/40">Recent 500s</span>
              <span className={data.status.recent_500_errors > 0 ? 'text-red-400' : 'text-green-400'}>
                {data.status.recent_500_errors}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-200/40">Total Blobs</span>
              <span className="text-parchment-200/70">{formatNumber(data.cards.total_blobs)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
