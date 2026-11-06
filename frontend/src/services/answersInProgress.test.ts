import { afterEach, describe, expect, it, vi } from 'vitest';
import { answersInProgress } from './answersInProgress';

afterEach(() => answersInProgress.reset());

describe('answersInProgress: answers that keep going after the user leaves the chat', () => {
  it('tracks a running answer and the text it has produced so far', () => {
    answersInProgress.start('chat-a', vi.fn());
    answersInProgress.setStreamId('chat-a', 'stream-1');
    answersInProgress.append('chat-a', 'Convergent ');
    answersInProgress.append('chat-a', 'Invoicing');

    expect(answersInProgress.isRunning('chat-a')).toBe(true);
    expect(answersInProgress.isRunning('chat-b')).toBe(false);
    expect(answersInProgress.get('chat-a')).toMatchObject({ streamId: 'stream-1', text: 'Convergent Invoicing' });
  });

  it('tells subscribers when an answer finishes, once', () => {
    const seen: string[] = [];
    const unsubscribe = answersInProgress.subscribe((chatId) => seen.push(chatId));
    answersInProgress.start('chat-a', vi.fn());

    answersInProgress.finish('chat-a');
    answersInProgress.finish('chat-a');
    unsubscribe();
    answersInProgress.start('chat-b', vi.fn());
    answersInProgress.finish('chat-b');

    expect(seen).toEqual(['chat-a']);
    expect(answersInProgress.isRunning('chat-a')).toBe(false);
  });

  it('keeps a background failure until the chat is opened', () => {
    answersInProgress.start('chat-a', vi.fn());
    answersInProgress.finish('chat-a', 'Generation interrupted. Please try again.');

    expect(answersInProgress.takeFailure('chat-a')).toBe('Generation interrupted. Please try again.');
    expect(answersInProgress.takeFailure('chat-a')).toBeUndefined();
  });

  it('stop aborts the request and hands back what is needed to save the partial answer', () => {
    const abort = vi.fn();
    const seen: string[] = [];
    answersInProgress.subscribe((chatId) => seen.push(chatId));
    answersInProgress.start('chat-a', abort);
    answersInProgress.setStreamId('chat-a', 'stream-1');
    answersInProgress.append('chat-a', 'Partial');

    expect(answersInProgress.stop('chat-a')).toMatchObject({ streamId: 'stream-1', text: 'Partial' });
    expect(abort).toHaveBeenCalledOnce();
    expect(answersInProgress.isRunning('chat-a')).toBe(false);
    expect(seen).toEqual([]); // a stopped answer is saved by the caller, not reloaded
    expect(answersInProgress.stop('chat-a')).toBeUndefined();
  });

  it('remembers chats whose answer ended in this page session, so a reload is not mistaken for one still running', () => {
    expect(answersInProgress.endedHere('chat-a')).toBe(false);

    answersInProgress.start('chat-a', vi.fn());
    expect(answersInProgress.endedHere('chat-a')).toBe(false);
    answersInProgress.finish('chat-a', 'Generation interrupted. Please try again.');
    expect(answersInProgress.endedHere('chat-a')).toBe(true);

    answersInProgress.start('chat-b', vi.fn());
    answersInProgress.stop('chat-b');
    answersInProgress.start('chat-c', vi.fn());
    answersInProgress.remove('chat-c');
    // A stream that failed before the server sent its id never had an entry.
    answersInProgress.markEnded('chat-d');
    expect(['chat-b', 'chat-c', 'chat-d'].map((id) => answersInProgress.endedHere(id))).toEqual([true, true, true]);

    // A new answer in the same chat is running again, not ended.
    answersInProgress.start('chat-a', vi.fn());
    expect(answersInProgress.endedHere('chat-a')).toBe(false);
    expect(answersInProgress.endedHere(undefined)).toBe(false);
  });

  it('remove forgets an answer without notifying (the visible Stop path saves it itself)', () => {
    const seen: string[] = [];
    answersInProgress.subscribe((chatId) => seen.push(chatId));
    answersInProgress.start('chat-a', vi.fn());
    answersInProgress.remove('chat-a');
    expect(answersInProgress.isRunning('chat-a')).toBe(false);
    expect(seen).toEqual([]);
  });
});
