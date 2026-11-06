import type { Chat } from '../types';

interface ChatListHandlers {
  onLoaded: (chats: Chat[]) => void;
  /** The list could not be loaded; the caller keeps the list it already shows and offers a retry. */
  onFailed: () => void;
}

/**
 * Returns a refresh function for the sidebar chat list. Only the latest refresh's result is applied, so
 * a slow older response cannot overwrite a newer list (or flag an error after a newer success).
 */
export function createChatListLoader(load: () => Promise<Chat[]>, { onLoaded, onFailed }: ChatListHandlers): () => Promise<void> {
  let latest = 0;
  return async () => {
    const request = ++latest;
    try {
      const chats = await load();
      if (request === latest) onLoaded(chats);
    } catch {
      if (request === latest) onFailed();
    }
  };
}
