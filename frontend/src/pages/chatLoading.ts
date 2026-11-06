import type { Message } from '../types';

/** A question newer than this, still without an answer after a page load, is shown as "Still generating". */
export const STILL_GENERATING_WINDOW_MS = 3 * 60 * 1000;
export const ANSWER_POLL_INTERVAL_MS = 3000;
/** How long the chat keeps checking for that answer before it stops waiting. */
export const ANSWER_WAIT_MS = 3 * 60 * 1000;

export type ChatLoadResult = { status: 'loaded'; messages: Message[] } | { status: 'failed' } | { status: 'stale' };

/**
 * Loads a chat's messages for the chat page. The result is `stale` when the user has opened another chat
 * in the meantime, so a slow response can never show one chat's messages under another chat.
 */
export async function loadChatForScreen(
  chatId: string,
  load: (chatId: string) => Promise<Message[]>,
  isCurrent: (chatId: string) => boolean,
): Promise<ChatLoadResult> {
  try {
    const messages = await load(chatId);
    return isCurrent(chatId) ? { status: 'loaded', messages } : { status: 'stale' };
  } catch {
    return isCurrent(chatId) ? { status: 'failed' } : { status: 'stale' };
  }
}

/** Server timestamps are UTC; those without a zone (naive datetimes) are read as UTC, not local time. */
export function parseServerTime(value: string): number {
  if (!value) return Number.NaN;
  const normalized = value.trim().replace(/(\.\d{3})\d+/, '$1');
  const hasZone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(normalized);
  return Date.parse(hasZone ? normalized : `${normalized}Z`);
}

const endsWithQuestion = (messages: Message[]) => messages.length > 0 && messages[messages.length - 1].role === 'user';

/**
 * After a page load: the chat ends with a question that has no answer yet and was asked less than three
 * minutes ago, so its answer is most likely still being generated on the server.
 */
export function isAnswerPendingAfterReload(
  messages: Message[],
  nowMs: number,
  windowMs: number = STILL_GENERATING_WINDOW_MS,
): boolean {
  if (!endsWithQuestion(messages)) return false;
  const askedAt = parseServerTime(messages[messages.length - 1].created_at);
  return Number.isFinite(askedAt) && nowMs - askedAt < windowMs;
}

interface PollOptions {
  load: () => Promise<Message[]>;
  /** The answer arrived: the chat's messages including it. */
  onAnswer: (messages: Message[]) => void;
  /** No answer within `waitMs`. */
  onGiveUp: () => void;
  intervalMs?: number;
  waitMs?: number;
  now?: () => number;
}

/**
 * Reloads the chat every few seconds until its last message is an answer, or gives up after `waitMs`.
 * One request at a time; failed requests count as "not yet". Returns a cancel function.
 */
export function pollForAnswer({
  load,
  onAnswer,
  onGiveUp,
  intervalMs = ANSWER_POLL_INTERVAL_MS,
  waitMs = ANSWER_WAIT_MS,
  now = Date.now,
}: PollOptions): () => void {
  const startedAt = now();
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const tick = async () => {
    let messages: Message[] | null = null;
    try {
      messages = await load();
    } catch {
      messages = null;
    }
    if (cancelled) return;
    if (messages && messages.length > 0 && !endsWithQuestion(messages)) {
      onAnswer(messages);
      return;
    }
    if (now() - startedAt >= waitMs) {
      onGiveUp();
      return;
    }
    timer = setTimeout(tick, intervalMs);
  };

  timer = setTimeout(tick, intervalMs);
  return () => {
    cancelled = true;
    clearTimeout(timer);
  };
}
