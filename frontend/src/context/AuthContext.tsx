import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
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
  setUnauthorizedHandler,
  TOKEN_STORAGE_KEY,
} from '../services/api';
import { clearAllUserStorage, clearLegacyUserStorage, clearUserStorage, userStorageKey } from '../services/userStorage';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  adminLogin: (email: string, password: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    password: string,
    inviteCode?: string
  ) => Promise<void>;
  updateProfile: (updates: { name: string; dateOfBirth?: string; avatar?: string }) => void;
  logout: () => void;
}


const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [loading, setLoading] = useState<boolean>(true);
  const userIdRef = useRef<string | null>(null);

  const saveUser = (next: User) => {
    userIdRef.current = next.id;
    localStorage.setItem(userStorageKey(next.id, 'profile'), JSON.stringify(next));
    setUser(next);
  };

  const clearCurrentUserStorage = () => {
    if (userIdRef.current) clearUserStorage(userIdRef.current);
    clearLegacyUserStorage();
    userIdRef.current = null;
  };

  useEffect(() => {
    const initAuth = async () => {
      clearLegacyUserStorage();
      const stored = getStoredToken();

      if (stored) {
        try {
          const userData = await apiGetMe();
          userIdRef.current = userData.id;
          const savedLocalProfile = localStorage.getItem(userStorageKey(userData.id, 'profile'));
          let extra: { dateOfBirth?: string; avatar?: string } = {};
          if (savedLocalProfile) {
            try {
              const cached = JSON.parse(savedLocalProfile);
              extra = { dateOfBirth: cached.dateOfBirth, avatar: cached.avatar };
            } catch {}
          }
          saveUser({ ...userData, profileCompleted: true, ...extra });
          setToken(stored);
        } catch (error) {
          console.error('Authentication initialization failed:', error);
          const status = error instanceof ApiError ? error.status : undefined;
          if (status === 401 || status === 403) {
            // The server rejected the token (expired or signed with an old secret). Restoring the
            // cached profile would look signed in while every chat request fails, so sign out.
            clearStoredToken();
            clearAllUserStorage();
            userIdRef.current = null;
            setToken(null);
            setUser(null);
          } else {
            clearStoredToken();
            clearAllUserStorage();
            userIdRef.current = null;
            setToken(null);
            setUser(null);
          }
        }
      } else {
        setUser(null);
      }

      setLoading(false);
    };

    initAuth();
  }, []);

  // An authenticated request answered 401: the session ended (expiry, logout elsewhere, revoked).
  // Clear it everywhere and go back to the right sign-in page instead of failing request by request.
  useEffect(() => {
    let handled = false;
    setUnauthorizedHandler(() => {
      if (handled) return;
      handled = true;
      clearStoredToken();
      clearCurrentUserStorage();
      setToken(null);
      setUser(null);
      const signIn = window.location.pathname.startsWith('/admin') ? '/admin/login' : '/login';
      if (!window.location.pathname.startsWith(signIn)) {
        window.location.assign(`${signIn}?expired=1`);
      }
    });
    // Signing out (or in as someone else) in another tab ends this tab's session too.
    const onStorage = (event: StorageEvent) => {
      if (event.key !== TOKEN_STORAGE_KEY) return;
      if (!event.newValue) {
        clearCurrentUserStorage();
        setToken(null);
        setUser(null);
      } else if (event.oldValue && event.newValue !== event.oldValue) {
        window.location.reload();
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      setUnauthorizedHandler(null);
      window.removeEventListener('storage', onStorage);
    };
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
    saveUser(enrichedUser);
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
    saveUser(enrichedUser);
  };


  const register = async (
    name: string,
    email: string,
    password: string,
    inviteCode?: string
  ): Promise<void> => {
    const data = await apiRegister(
      name,
      email,
      password,
      inviteCode
    );

    setStoredToken(data.access_token);
    setToken(data.access_token);
    const enrichedUser: User = {
      ...data.user,
      profileCompleted: true,
    };
    saveUser(enrichedUser);
  };

  const updateProfile = (updates: { name: string; dateOfBirth?: string; avatar?: string }) => {
    if (!user) return;
    saveUser({ ...user, ...updates, profileCompleted: true });
  };

  const logout = (): void => {
    void apiLogout().catch(() => undefined);
    clearStoredToken();
    clearCurrentUserStorage();
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
