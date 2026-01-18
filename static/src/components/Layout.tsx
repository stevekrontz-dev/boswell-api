import { useState } from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/dashboard/mindstate', label: 'Mindstate' },
    { to: '/dashboard/connect', label: 'Connect' },
    { to: '/dashboard/branches', label: 'Branches' },
    { to: '/dashboard/billing', label: 'Billing' },
  ];

  const isFullWidth = location.pathname === '/dashboard/mindstate';
  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="min-h-screen bg-ink-950">
      {/* Navigation */}
      <nav className="bg-ink-950/80 backdrop-blur-xl border-b border-parchment-200/5 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 md:px-6">
          <div className="flex items-center justify-between h-14 md:h-16">
            {/* Logo */}
            <Link to="/dashboard" className="flex items-center gap-2 md:gap-3">
              <img src="/boswell-logo-dark.svg" alt="Boswell" className="h-7 w-7 md:h-8 md:w-8" />
              <span className="font-display text-base md:text-lg text-parchment-50">
                Boswell
              </span>
            </Link>

            {/* Desktop Nav Links */}
            <div className="hidden md:flex items-center gap-1 bg-ink-900/50 rounded-full p-1 border border-parchment-200/10">
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

            {/* Desktop User Info */}
            <div className="hidden md:flex items-center gap-4">
              <span className="text-parchment-200/50 text-sm">{user?.email}</span>
              <button
                onClick={logout}
                className="text-sm text-parchment-200/60 hover:text-ember-500 transition-colors"
              >
                Logout
              </button>
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-parchment-200/60"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                  d={mobileMenuOpen ? "M6 18L18 6M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"} />
              </svg>
            </button>
          </div>

          {/* Mobile Menu */}
          {mobileMenuOpen && (
            <div className="md:hidden pb-4 border-t border-parchment-200/5 mt-2 pt-3">
              <div className="flex flex-col gap-1">
                {navLinks.map((link) => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileMenuOpen(false)}
                    className={
                      isActive(link.to)
                        ? 'px-4 py-2 rounded-lg text-sm font-medium bg-ember-500 text-ink-950'
                        : 'px-4 py-2 rounded-lg text-sm font-medium text-parchment-200/60 hover:bg-parchment-200/5'
                    }
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t border-parchment-200/5 px-4 flex items-center justify-between">
                <span className="text-parchment-200/50 text-xs truncate">{user?.email}</span>
                <button
                  onClick={logout}
                  className="text-sm text-parchment-200/60 hover:text-ember-500"
                >
                  Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Main Content */}
      <main className={isFullWidth ? '' : 'max-w-4xl mx-auto px-4 md:px-6 py-8 md:py-12'}>
        <Outlet />
      </main>
    </div>
  );
}
