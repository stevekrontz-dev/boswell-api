import { useState, useEffect } from 'react';
import { getAdminAlerts } from '../../lib/api';
import type { AdminAlert } from '../../lib/api';

export default function AdminAlertsPage() {
  const [alerts, setAlerts] = useState<AdminAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState({ critical: 0, warning: 0, info: 0 });

  const fetchAlerts = () => {
    getAdminAlerts()
      .then(d => {
        setAlerts(d.alerts);
        setCounts({
          critical: d.critical_count || 0,
          warning: d.warning_count || 0,
          info: d.alerts.filter(a => a.severity === 'info').length,
        });
        setError(null);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">System Alerts</h1>
        <div className="card p-6 animate-pulse">
          <div className="space-y-3">
            {[1,2].map(i => <div key={i} className="h-16 bg-parchment-200/5 rounded" />)}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl text-parchment-50">System Alerts</h1>
        <div className="card p-6 border-red-500/30">
          <p className="text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  const severityStyles = {
    critical: 'bg-red-950/30 border-red-500/20',
    warning: 'bg-amber-950/30 border-amber-500/20',
    info: 'bg-blue-950/30 border-blue-500/20',
  };

  const severityBadge = {
    critical: 'bg-red-500/20 text-red-400',
    warning: 'bg-amber-500/20 text-amber-400',
    info: 'bg-blue-500/20 text-blue-400',
  };

  const severityDot = {
    critical: 'bg-red-400',
    warning: 'bg-amber-400',
    info: 'bg-blue-400',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-2xl text-parchment-50">System Alerts</h1>
          {alerts.length > 0 && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-parchment-200/10 text-parchment-200/60">
              {alerts.length}
            </span>
          )}
        </div>
        <button
          onClick={() => { setLoading(true); fetchAlerts(); }}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-parchment-200/10 text-parchment-200/60 hover:bg-parchment-200/20 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Summary Pills */}
      {alerts.length > 0 && (
        <div className="flex gap-2">
          {counts.critical > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-red-500/20 text-red-400">
              {counts.critical} critical
            </span>
          )}
          {counts.warning > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-amber-500/20 text-amber-400">
              {counts.warning} warning{counts.warning !== 1 ? 's' : ''}
            </span>
          )}
          {counts.info > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-400">
              {counts.info} info
            </span>
          )}
        </div>
      )}

      {/* Alert Cards */}
      {alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map((alert, i) => (
            <div
              key={i}
              className={`p-4 rounded-lg border ${severityStyles[alert.severity]}`}
            >
              <div className="flex items-start gap-3">
                <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${severityDot[alert.severity]}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-medium ${severityBadge[alert.severity]}`}>
                      {alert.severity}
                    </span>
                    <span className="text-[10px] font-mono text-parchment-200/30">{alert.type}</span>
                  </div>
                  <p className="text-sm text-parchment-50">{alert.message}</p>
                  {alert.details && Object.keys(alert.details).length > 0 && (
                    <div className="mt-2 text-xs text-parchment-200/40 font-mono">
                      {Object.entries(alert.details).map(([k, v]) => (
                        <span key={k} className="mr-3">{k}: {String(v)}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <div className="text-4xl mb-3">&#10003;</div>
          <p className="text-parchment-50 font-medium">No alerts</p>
          <p className="text-sm text-parchment-200/40 mt-1">System is healthy</p>
        </div>
      )}
    </div>
  );
}
