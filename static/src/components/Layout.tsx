import { Link, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Logo from './Logo';

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
    <div className="min-h-screen bg-boswell-bg">
      {/* Navigation */}
      <nav className="bg-boswell-bg/80 backdrop-blur-xl border-b border-boswell-border sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/dashboard" className="flex items-center gap-3 group">
              <Logo size="sm" />
              <span className="font-display text-lg text-ember-500 group-hover:text-ember-400 transition-colors">
                Boswell
              </span>
            </Link>

            {/* Center Nav Links */}
            <div className="flex items-center gap-1 bg-boswell-card rounded-full p-1 border border-boswell-border">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={
                    isActive(link.to)
                      ? 'px-4 py-1.5 rounded-full text-sm font-medium bg-ember-500 text-boswell-bg transition-all duration-200'
                      : 'px-4 py-1.5 rounded-full text-sm font-medium text-gray-400 hover:text-white hover:bg-boswell-border transition-all duration-200'
                  }
                >
                  {link.label}
                </Link>
              ))}
            </div>

            {/* User Info */}
            <div className="flex items-center gap-4">
              <span className="text-gray-500 text-sm font-body">{user?.email}</span>
              <button
                onClick={logout}
                className="px-4 py-1.5 rounded-full text-sm font-medium text-gray-400 hover:text-ember-500 hover:bg-boswell-card border border-transparent hover:border-boswell-border transition-all duration-200"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
