import { Link, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navLinks = [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/dashboard/connect', label: 'Connect' },
    { to: '/dashboard/branches', label: 'Branches' },
    { to: '/dashboard/billing', label: 'Billing' },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="min-h-screen bg-slate-950">
      <nav className="bg-slate-900 border-b border-slate-800 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <Link to="/dashboard" className="text-orange-500 font-bold text-xl tracking-tight">
                Boswell
              </Link>
              <span className="text-slate-500 text-sm font-medium px-2 py-0.5 bg-slate-800 rounded">
                Dashboard
              </span>
            </div>

            <div className="flex items-center gap-1">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={isActive(link.to)
                    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-slate-800 text-orange-400'
                    : 'px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors'
                  }
                >
                  {link.label}
                </Link>
              ))}
            </div>

            <div className="flex items-center gap-4">
              <span className="text-slate-400 text-sm">{user?.email}</span>
              <button
                onClick={logout}
                className="text-slate-500 hover:text-slate-300 text-sm"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
