import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAllUserStorage, clearLegacyUserStorage, clearUserStorage, userStorageKey } from './userStorage';
import { projectService } from './projectService';

const values = new Map<string, string>();

beforeEach(() => {
  values.clear();
  vi.stubGlobal('localStorage', {
    get length() { return values.size; },
    key: (index: number) => [...values.keys()][index] ?? null,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('user-scoped browser storage', () => {
  it('isolates each account project data', () => {
    projectService.createProject('user one', 'Private project');
    expect(projectService.getProjects('user two').map((project) => project.name)).toEqual(['SAP BRIM Architecture']);
    expect(projectService.getProjects('user one').map((project) => project.name)).toContain('Private project');
  });

  it('clears only the current user on logout', () => {
    localStorage.setItem(userStorageKey('one', 'projects'), '[]');
    localStorage.setItem(userStorageKey('one', 'profile'), '{}');
    localStorage.setItem(userStorageKey('two', 'projects'), '["private"]');
    localStorage.setItem('clyptus_projects', '["legacy"]');

    clearUserStorage('one');
    clearLegacyUserStorage();

    expect(localStorage.getItem(userStorageKey('one', 'profile'))).toBeNull();
    expect(localStorage.getItem(userStorageKey('two', 'projects'))).toBe('["private"]');
    expect(localStorage.getItem('clyptus_projects')).toBeNull();
  });

  it('clears all account-scoped data after an invalid session', () => {
    localStorage.setItem(userStorageKey('one', 'projects'), '[]');
    localStorage.setItem(userStorageKey('two', 'profile'), '{}');
    clearAllUserStorage();
    expect(values.size).toBe(0);
  });
});
