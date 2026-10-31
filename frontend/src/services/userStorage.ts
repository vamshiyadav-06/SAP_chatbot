const USER_STORAGE_PREFIX = 'clyptus:user:';

const LEGACY_UNSCOPED_KEYS = [
  'clyptus_demo_user',
  'clyptus_projects',
  'clyptus_pinned_chats',
  'sap_assistant_pinned',
  'sap_assistant_archived',
];

export function userStorageKey(userId: string, key: string): string {
  return `${USER_STORAGE_PREFIX}${encodeURIComponent(userId)}:${key}`;
}

export function clearUserStorage(userId: string): void {
  const prefix = `${USER_STORAGE_PREFIX}${encodeURIComponent(userId)}:`;
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(prefix)) localStorage.removeItem(key);
  }
}

export function clearAllUserStorage(): void {
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(USER_STORAGE_PREFIX)) localStorage.removeItem(key);
  }
  clearLegacyUserStorage();
}

export function clearLegacyUserStorage(): void {
  LEGACY_UNSCOPED_KEYS.forEach((key) => localStorage.removeItem(key));
}
