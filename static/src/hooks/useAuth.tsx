import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { login as apiLogin, register as apiRegister, getCurrentUser } from '../lib/api';

interface User {
  id: string;
  email: string;
  name: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  loginWithToken: (token: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string, name: string, agreedToTerms: boolean) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('boswell_token');
    const storedUser = localStorage.getItem('boswell_user');
    if (storedToken && storedUser) {
      setToken(storedToken);
      setUser(JSON.parse(storedUser));
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const data = await apiLogin(email, password);
      if (data.token) {
        setToken(data.token);
        setUser(data.user);
        localStorage.setItem('boswell_token', data.token);
        localStorage.setItem('boswell_user', JSON.stringify(data.user));
        localStorage.setItem('boswell_user_email', email); // Store for passkey login
        return { success: true };
      }
      return { success: false, error: data.error || 'Login failed' };
    } catch {
      return { success: false, error: 'Network error' };
    }
  };

  const loginWithToken = async (sessionToken: string) => {
    try {
      // The session token from passkey auth needs to fetch user info
      // We'll use it to get the current user profile
      const userProfile = await getCurrentUser(sessionToken);
      if (userProfile && userProfile.id) {
        const userData = {
          id: userProfile.id,
          email: userProfile.email,
          name: userProfile.name || userProfile.email,
        };
        setToken(sessionToken);
        setUser(userData);
        localStorage.setItem('boswell_token', sessionToken);
        localStorage.setItem('boswell_user', JSON.stringify(userData));
        return { success: true };
      }
      return { success: false, error: 'Failed to get user profile' };
    } catch {
      return { success: false, error: 'Network error' };
    }
  };

  const register = async (email: string, password: string, name: string, agreedToTerms: boolean) => {
    try {
      const data = await apiRegister(email, password, name, agreedToTerms);
      if (data.token) {
        setToken(data.token);
        setUser(data.user);
        localStorage.setItem('boswell_token', data.token);
        localStorage.setItem('boswell_user', JSON.stringify(data.user));
        localStorage.setItem('boswell_user_email', email); // Store for passkey login
        return { success: true };
      }
      return { success: false, error: data.error || 'Registration failed' };
    } catch {
      return { success: false, error: 'Network error' };
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('boswell_token');
    localStorage.removeItem('boswell_user');
    // Keep boswell_user_email for passkey login
  };

  return (
    <AuthContext.Provider value={{ user, token, login, loginWithToken, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
