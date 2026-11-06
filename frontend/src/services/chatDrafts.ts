import { userStorageKey } from './userStorage';

// Unsent message-box text, one per chat plus one for the new-chat screen, scoped to the signed-in account.
// Kept in sessionStorage (this tab only) so it survives a refresh and an expired session that sends the user
// to sign in again, but not closing the tab. Signing out from the menu clears the account's drafts.

const DRAFT_PREFIX = 'chat_draft:';
const NEW_CHAT = 'new';

/** Storage key of the draft for one chat (or the new-chat screen); null without a signed-in account. */
export function chatDraftKey(userId: string | null | undefined, chatId: string | null | undefined): string | null {
  if (!userId) return null;
  return userStorageKey(userId, `${DRAFT_PREFIX}${chatId || NEW_CHAT}`);
}

export function readDraft(key: string | null): string {
  if (!key) return '';
  try {
    return sessionStorage.getItem(key) ?? '';
  } catch {
    return '';
  }
}

/** Saves the draft; blank text removes it. */
export function writeDraft(key: string | null, text: string): void {
  if (!key) return;
  try {
    if (text.trim()) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  } catch {
    // Typing keeps working when browser storage is unavailable; only the draft is not kept.
  }
}

/** Removes the draft once `sentText` was sent, unless a different draft has been typed since. */
export function clearDraft(key: string | null, sentText: string): void {
  if (!key) return;
  try {
    const stored = sessionStorage.getItem(key);
    if (stored !== null && stored.trim() === sentText.trim()) sessionStorage.removeItem(key);
  } catch {
    // Nothing stored that could be cleared.
  }
}

/** Removes every draft of one account (explicit sign-out). */
export function clearUserDrafts(userId: string): void {
  const prefix = userStorageKey(userId, DRAFT_PREFIX);
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(prefix)) sessionStorage.removeItem(key);
    }
  } catch {
    // Storage unavailable: nothing was saved.
  }
}
