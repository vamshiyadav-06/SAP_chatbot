import React, {
  createContext,
  useContext,
  useState,
  useEffect,
} from 'react';

import type { User } from '../types';

import {
  apiGetMe,
  apiLogin,
  apiDemoLogin,
  apiRegister,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
} from '../services/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    password: string
  ) => Promise<void>;
  guestLogin: () => Promise<void>;
  updateProfile: (updates: { name: string; dateOfBirth?: string; avatar?: string }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const LOCAL_USER_KEY = 'clyptus_demo_user';

export const AuthProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const stored = getStoredToken();

      if (stored) {
        try {
          const userData = await apiGetMe();
          const savedLocalProfile = localStorage.getItem(LOCAL_USER_KEY);
          let extra = {};
          if (savedLocalProfile) {
            try { extra = JSON.parse(savedLocalProfile); } catch {}
          }
          setUser({ ...userData, profileCompleted: true, ...extra });
          setToken(stored);
        } catch (error) {
          console.error('Authentication initialization failed:', error);
          // Check if there is a cached guest/local session
          const savedLocal = localStorage.getItem(LOCAL_USER_KEY);
          if (savedLocal) {
            try {
              const parsed = JSON.parse(savedLocal);
              setUser(parsed);
            } catch {
              clearStoredToken();
              setToken(null);
              setUser(null);
            }
          } else {
            clearStoredToken();
            setToken(null);
            setUser(null);
          }
        }
      } else {
        const savedLocal = localStorage.getItem(LOCAL_USER_KEY);
        if (savedLocal) {
          try {
            setUser(JSON.parse(savedLocal));
          } catch {}
        }
      }

      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (
    email: string,
    password: string
  ): Promise<void> => {
    const data = await apiLogin(email, password);

    setStoredToken(data.access_token);
    setToken(data.access_token);
    const enrichedUser: User = {
      ...data.user,
      isGuest: false,
      profileCompleted: true,
    };
    setUser(enrichedUser);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
    // Reset guest trial count on real login
    localStorage.removeItem('clyptus_trial_query_count');
  };

  const register = async (
    name: string,
    email: string,
    password: string
  ): Promise<void> => {
    const data = await apiRegister(
      name,
      email,
      password
    );

    setStoredToken(data.access_token);
    setToken(data.access_token);
    const enrichedUser: User = {
      ...data.user,
      isGuest: false,
      profileCompleted: true,
    };
    setUser(enrichedUser);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
    // Reset guest trial count on real registration
    localStorage.removeItem('clyptus_trial_query_count');
  };

  const guestLogin = async () => {
    try {
      const data = await apiDemoLogin();
      setStoredToken(data.access_token);
      setToken(data.access_token);
      const enrichedUser: User = {
        ...data.user,
        isGuest: true,
        profileCompleted: true,
      };
      setUser(enrichedUser);
      localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
    } catch (err) {
      console.warn('Backend demo endpoint unavailable, using offline fallback', err);
      const guestUser: User = {
        id: 'usr_guest_' + Date.now().toString(36),
        name: 'SAP Consultant',
        email: 'consultant@clyptusap.ai',
        is_admin: false,
        isGuest: true,
        profileCompleted: true,
        created_at: new Date().toISOString(),
      };
      setUser(guestUser);
      localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(guestUser));
    }
  };

  const updateProfile = (updates: { name: string; dateOfBirth?: string; avatar?: string }) => {
    setUser((prev) => {
      const updated: User = prev
        ? { ...prev, ...updates, profileCompleted: true }
        : {
            id: 'usr_' + Date.now().toString(36),
            email: 'user@clyptusap.ai',
            name: updates.name,
            dateOfBirth: updates.dateOfBirth,
            avatar: updates.avatar,
            profileCompleted: true,
          };
      localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(updated));
      return updated;
    });
  };

  const logout = (): void => {
    clearStoredToken();
    localStorage.removeItem(LOCAL_USER_KEY);
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        login,
        register,
        guestLogin,
        updateProfile,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      'useAuth must be used within an AuthProvider'
    );
  }

  return context;
};