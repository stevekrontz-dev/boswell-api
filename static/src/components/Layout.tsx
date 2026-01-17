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
    <div className="min-h-screen bg-ink-950">
      {/* Navigation */}
      <nav className="bg-ink-950/80 backdrop-blur-xl border-b border-parchment-200/5 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/dashboard" className="flex items-center gap-3">
              <img src="/boswell-logo-dark.svg" alt="Boswell" className="h-8 w-8" />
              <span className="font-display text-lg text-parchment-50">
                Boswell
              </span>
            </Link>

            {/* Center Nav Links */}
            <div className="flex items-center gap-1 bg-ink-900/50 rounded-full p-1 border border-parchment-200/10">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={
                    isActive(link.to)
                      ? 'px-4 py-1.5 rounded-full text-sm font-medium bg-ember-500 text-ink-950 transition-all duration-200'
                      : 'px-4 py-1.5 rounded-full text-sm font-medium text-parchment-200/60 hover:text-parchment-50 hover:bg-parchment-200/5 transition-all duration-200'
                  }
                >
                  {link.label}
                </Link>
              ))}
            </div>

            {/* User Info */}
            <div className="flex items-center gap-4">
              <span className="text-parchment-200/50 text-sm">{user?.email}</span>
              <button
                onClick={logout}
                className="text-sm text-parchment-200/60 hover:text-ember-500 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-12">
        <Outlet />
      </main>
    </div>
  );
}
