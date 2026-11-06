// Answers that keep generating after the user leaves their chat (opens another chat, starts a new one or
// goes to another page). The request keeps running; the server finishes and saves the answer either way.
// The chat page asks this store whether the chat it shows still has an answer coming, and is told when it
// arrives so it can reload the messages. Only the Stop button ends an answer early.

export interface AnswerInProgress {
  /** Server-issued id of the stream; needed to save a stopped answer. */
  streamId: string | null;
  /** The answer text received so far. */
  text: string;
  abort: () => void;
}

type Listener = (chatId: string) => void;

const running = new Map<string, AnswerInProgress>();
const failures = new Map<string, string>();
// Chats whose latest answer ended (arrived, failed or was stopped) while this page was open. After a page
// reload this is empty, which is how the chat page tells a reload apart from a same-session visit.
const ended = new Set<string>();
const listeners = new Set<Listener>();

export const answersInProgress = {
  start(chatId: string, abort: () => void): void {
    running.set(chatId, { streamId: null, text: '', abort });
    ended.delete(chatId);
  },

  setStreamId(chatId: string, streamId: string): void {
    const entry = running.get(chatId);
    if (entry) entry.streamId = streamId;
  },

  append(chatId: string, text: string): void {
    const entry = running.get(chatId);
    if (entry) entry.text += text;
  },

  get(chatId: string): AnswerInProgress | undefined {
    return running.get(chatId);
  },

  isRunning(chatId: string | undefined): boolean {
    return Boolean(chatId && running.has(chatId));
  },

  /** The answer arrived (or failed): forget it and tell whoever shows that chat. */
  finish(chatId: string, failure?: string): void {
    if (chatId) ended.add(chatId);
    if (!running.delete(chatId)) return;
    if (failure) failures.set(chatId, failure);
    listeners.forEach((listener) => listener(chatId));
  },

  /** A failure that happened while nobody was looking at the chat; returned once. */
  takeFailure(chatId: string): string | undefined {
    const failure = failures.get(chatId);
    failures.delete(chatId);
    return failure;
  },

  /** Stop a background answer: aborts the request and returns what is needed to save the partial answer. */
  stop(chatId: string): AnswerInProgress | undefined {
    const entry = running.get(chatId);
    if (!entry) return undefined;
    running.delete(chatId);
    ended.add(chatId);
    entry.abort();
    return entry;
  },

  /** Forget an answer without telling anyone (the visible Stop button saves it itself). */
  remove(chatId: string): void {
    running.delete(chatId);
    ended.add(chatId);
  },

  /** An answer ended before it was tracked here (e.g. it failed before the server sent a stream id). */
  markEnded(chatId: string): void {
    if (chatId) ended.add(chatId);
  },

  /** The chat's latest answer ended while this page was open (so nothing is still generating for it). */
  endedHere(chatId: string | undefined): boolean {
    return Boolean(chatId && ended.has(chatId));
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  /** Tests only. */
  reset(): void {
    running.clear();
    failures.clear();
    ended.clear();
    listeners.clear();
  },
};
