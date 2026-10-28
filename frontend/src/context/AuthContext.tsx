import React, {
  createContext,
  useContext,
  useState,
  useEffect,
} from 'react';

import type { User } from '../types';

import {
  ApiError,
  apiGetMe,
  apiLogout,
  apiLogin,
  apiAdminLogin,
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
  adminLogin: (email: string, password: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    password: string
  ) => Promise<void>;
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
          let extra: { dateOfBirth?: string; avatar?: string } = {};
          if (savedLocalProfile) {
            try {
              const cached = JSON.parse(savedLocalProfile);
              extra = { dateOfBirth: cached.dateOfBirth, avatar: cached.avatar };
            } catch {}
          }
          setUser({ ...userData, profileCompleted: true, ...extra });
          setToken(stored);
        } catch (error) {
          console.error('Authentication initialization failed:', error);
          const status = error instanceof ApiError ? error.status : undefined;
          if (status === 401 || status === 403) {
            // The server rejected the token (expired or signed with an old secret). Restoring the
            // cached profile would look signed in while every chat request fails, so sign out.
            clearStoredToken();
            localStorage.removeItem(LOCAL_USER_KEY);
            setToken(null);
            setUser(null);
          } else {
            clearStoredToken();
            localStorage.removeItem(LOCAL_USER_KEY);
            setToken(null);
            setUser(null);
          }
        }
      } else {
        localStorage.removeItem(LOCAL_USER_KEY);
        setUser(null);
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
      profileCompleted: true,
    };
    setUser(enrichedUser);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
  };

  const adminLogin = async (
    email: string,
    password: string
  ): Promise<void> => {
    const data = await apiAdminLogin(email, password);

    setStoredToken(data.access_token);
    setToken(data.access_token);
    const enrichedUser: User = {
      ...data.user,
      profileCompleted: true,
    };
    setUser(enrichedUser);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
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
      profileCompleted: true,
    };
    setUser(enrichedUser);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(enrichedUser));
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
    void apiLogout().catch(() => undefined);
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
        adminLogin,
        register,
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
