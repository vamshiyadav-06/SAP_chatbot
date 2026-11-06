import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '../types';
import {
  ANSWER_POLL_INTERVAL_MS,
  ANSWER_WAIT_MS,
  isAnswerPendingAfterReload,
  loadChatForScreen,
  parseServerTime,
  pollForAnswer,
} from './chatLoading';

const msg = (role: Message['role'], created_at: string, id = `${role}-${created_at}`): Message => ({
  id,
  chat_id: 'chat-a',
  role,
  content: `${role} text`,
  created_at,
  citations: [],
  web_sources: [],
});

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('loadChatForScreen: messages only reach the chat that is still on screen', () => {
  it('returns the loaded messages while the chat is still open', async () => {
    const messages = [msg('user', '2026-11-04T10:00:00')];
    await expect(loadChatForScreen('chat-a', () => Promise.resolve(messages), () => true)).resolves.toEqual({
      status: 'loaded',
      messages,
    });
  });

  it("drops chat A's messages when the user switched to chat B before they arrived", async () => {
    let current = 'chat-a';
    const pending = deferred<Message[]>();
    const result = loadChatForScreen('chat-a', () => pending.promise, (id) => id === current);
    current = 'chat-b';
    pending.resolve([msg('user', '2026-11-04T10:00:00')]);
    await expect(result).resolves.toEqual({ status: 'stale' });
  });

  it('reports a failed load (instead of an empty chat) only for the chat on screen', async () => {
    await expect(loadChatForScreen('chat-a', () => Promise.reject(new Error('500')), () => true)).resolves.toEqual({
      status: 'failed',
    });
    await expect(loadChatForScreen('chat-a', () => Promise.reject(new Error('500')), () => false)).resolves.toEqual({
      status: 'stale',
    });
  });
});

describe('parseServerTime', () => {
  it('reads server timestamps without a zone as UTC', () => {
    expect(parseServerTime('2026-11-04T10:00:00')).toBe(Date.UTC(2026, 10, 4, 10, 0, 0));
    expect(parseServerTime('2026-11-04T10:00:00.123456')).toBe(Date.UTC(2026, 10, 4, 10, 0, 0, 123));
  });

  it('keeps an explicit zone', () => {
    expect(parseServerTime('2026-11-04T10:00:00Z')).toBe(Date.UTC(2026, 10, 4, 10, 0, 0));
    expect(parseServerTime('2026-11-04T15:30:00+05:30')).toBe(Date.UTC(2026, 10, 4, 10, 0, 0));
  });

  it('returns NaN for missing or invalid values', () => {
    expect(parseServerTime('')).toBeNaN();
    expect(parseServerTime('not a date')).toBeNaN();
  });
});

describe('isAnswerPendingAfterReload: a question still waiting for its answer after a refresh', () => {
  const now = Date.UTC(2026, 10, 4, 10, 2, 0);

  it('is pending when the last message is a recent question', () => {
    const messages = [msg('user', '2026-11-04T09:00:00'), msg('assistant', '2026-11-04T09:00:30'), msg('user', '2026-11-04T10:00:30')];
    expect(isAnswerPendingAfterReload(messages, now)).toBe(true);
  });

  it('is not pending once an answer follows the question', () => {
    expect(isAnswerPendingAfterReload([msg('user', '2026-11-04T10:01:00'), msg('assistant', '2026-11-04T10:01:30')], now)).toBe(false);
  });

  it('is not pending when the question is three minutes old or more', () => {
    expect(isAnswerPendingAfterReload([msg('user', '2026-11-04T09:59:00')], now)).toBe(false);
    expect(isAnswerPendingAfterReload([msg('user', '2026-11-04T09:59:01')], now)).toBe(true);
  });

  it('is not pending for an empty chat or an unreadable timestamp', () => {
    expect(isAnswerPendingAfterReload([], now)).toBe(false);
    expect(isAnswerPendingAfterReload([msg('user', 'garbage')], now)).toBe(false);
  });
});

describe('pollForAnswer: waits for an answer generated while the page was reloaded', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const question = msg('user', '2026-11-04T10:00:00', 'q1');
  const answer = msg('assistant', '2026-11-04T10:00:40', 'a1');

  it('polls every 3 seconds and hands over the messages once the answer is there', async () => {
    const load = vi.fn<() => Promise<Message[]>>()
      .mockResolvedValueOnce([question])
      .mockResolvedValueOnce([question, answer]);
    const onAnswer = vi.fn();
    const onGiveUp = vi.fn();
    pollForAnswer({ load, onAnswer, onGiveUp });

    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS - 1);
    expect(load).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(load).toHaveBeenCalledTimes(1);
    expect(onAnswer).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledTimes(2);
    expect(onAnswer).toHaveBeenCalledWith([question, answer]);

    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS * 5);
    expect(load).toHaveBeenCalledTimes(2);
    expect(onGiveUp).not.toHaveBeenCalled();
  });

  it('keeps polling through failed requests and gives up after three minutes', async () => {
    const load = vi.fn<() => Promise<Message[]>>(() => Promise.reject(new Error('offline')));
    const onAnswer = vi.fn();
    const onGiveUp = vi.fn();
    pollForAnswer({ load, onAnswer, onGiveUp });

    await vi.advanceTimersByTimeAsync(ANSWER_WAIT_MS - 1);
    expect(onGiveUp).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS);
    expect(onGiveUp).toHaveBeenCalledTimes(1);
    const calls = load.mock.calls.length;
    expect(calls).toBe(ANSWER_WAIT_MS / ANSWER_POLL_INTERVAL_MS);

    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS * 10);
    expect(load).toHaveBeenCalledTimes(calls);
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it('stops for good when cancelled (chat switch or leaving the page), even mid-request', async () => {
    const pending = deferred<Message[]>();
    const load = vi.fn(() => pending.promise);
    const onAnswer = vi.fn();
    const onGiveUp = vi.fn();
    const cancel = pollForAnswer({ load, onAnswer, onGiveUp });

    await vi.advanceTimersByTimeAsync(ANSWER_POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledTimes(1);
    cancel();
    pending.resolve([question, answer]);
    await vi.advanceTimersByTimeAsync(ANSWER_WAIT_MS);

    expect(load).toHaveBeenCalledTimes(1);
    expect(onAnswer).not.toHaveBeenCalled();
    expect(onGiveUp).not.toHaveBeenCalled();
  });
});
