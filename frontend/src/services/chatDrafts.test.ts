import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { chatDraftKey, clearDraft, clearUserDrafts, readDraft, writeDraft } from './chatDrafts';
import { userStorageKey } from './userStorage';

const values = new Map<string, string>();

beforeEach(() => {
  values.clear();
  vi.stubGlobal('sessionStorage', {
    get length() { return values.size; },
    key: (index: number) => [...values.keys()][index] ?? null,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('chat drafts: unsent text kept per chat for the signed-in account', () => {
  it('scopes a draft key by account and chat, with one slot for the new-chat screen', () => {
    expect(chatDraftKey('one', 'chat-a')).toBe(userStorageKey('one', 'chat_draft:chat-a'));
    expect(chatDraftKey('one', undefined)).toBe(userStorageKey('one', 'chat_draft:new'));
    expect(chatDraftKey('one', 'chat-a')).not.toBe(chatDraftKey('two', 'chat-a'));
    expect(chatDraftKey(undefined, 'chat-a')).toBeNull();
  });

  it('restores what was typed in each chat separately', () => {
    writeDraft(chatDraftKey('one', 'chat-a'), 'How does CI billing work?');
    writeDraft(chatDraftKey('one', null), 'A new question');

    expect(readDraft(chatDraftKey('one', 'chat-a'))).toBe('How does CI billing work?');
    expect(readDraft(chatDraftKey('one', null))).toBe('A new question');
    expect(readDraft(chatDraftKey('one', 'chat-b'))).toBe('');
    expect(readDraft(chatDraftKey('two', 'chat-a'))).toBe('');
  });

  it('removes the stored draft when the text is emptied', () => {
    const key = chatDraftKey('one', 'chat-a');
    writeDraft(key, 'draft');
    writeDraft(key, '   ');
    expect(values.has(key!)).toBe(false);
  });

  it('clears a draft after it was sent, but not a newer draft typed meanwhile', () => {
    const key = chatDraftKey('one', 'chat-a');
    writeDraft(key, '  What is FI-CA?  ');
    clearDraft(key, 'What is FI-CA?');
    expect(readDraft(key)).toBe('');

    writeDraft(key, 'Next question being typed');
    clearDraft(key, 'What is FI-CA?');
    expect(readDraft(key)).toBe('Next question being typed');
  });

  it('clears every draft of one account on sign-out and keeps other accounts', () => {
    writeDraft(chatDraftKey('one', 'chat-a'), 'a');
    writeDraft(chatDraftKey('one', null), 'b');
    writeDraft(chatDraftKey('two', 'chat-a'), 'c');
    values.set(userStorageKey('one', 'other_setting'), 'kept');

    clearUserDrafts('one');

    expect(readDraft(chatDraftKey('one', 'chat-a'))).toBe('');
    expect(readDraft(chatDraftKey('one', null))).toBe('');
    expect(readDraft(chatDraftKey('two', 'chat-a'))).toBe('c');
    expect(values.get(userStorageKey('one', 'other_setting'))).toBe('kept');
  });

  it('keeps working when browser storage is unavailable', () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
      removeItem: () => { throw new Error('blocked'); },
      key: () => { throw new Error('blocked'); },
      get length(): number { throw new Error('blocked'); },
    });
    const key = chatDraftKey('one', 'chat-a');
    expect(() => writeDraft(key, 'x')).not.toThrow();
    expect(readDraft(key)).toBe('');
    expect(() => clearDraft(key, 'x')).not.toThrow();
    expect(() => clearUserDrafts('one')).not.toThrow();
  });
});
