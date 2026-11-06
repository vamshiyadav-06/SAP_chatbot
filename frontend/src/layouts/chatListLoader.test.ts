import { describe, expect, it, vi } from 'vitest';
import type { Chat } from '../types';
import { createChatListLoader } from './chatListLoader';

const chat = (id: string): Chat => ({ id, title: id, created_at: '2026-11-04T10:00:00', updated_at: '2026-11-04T10:00:00' });

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('createChatListLoader: the sidebar chat list', () => {
  it('hands over the loaded chats', async () => {
    const onLoaded = vi.fn();
    const onFailed = vi.fn();
    await createChatListLoader(() => Promise.resolve([chat('a')]), { onLoaded, onFailed })();
    expect(onLoaded).toHaveBeenCalledWith([chat('a')]);
    expect(onFailed).not.toHaveBeenCalled();
  });

  it('reports a failure without replacing the list already shown', async () => {
    const onLoaded = vi.fn();
    const onFailed = vi.fn();
    await createChatListLoader(() => Promise.reject(new Error('offline')), { onLoaded, onFailed })();
    expect(onFailed).toHaveBeenCalledOnce();
    expect(onLoaded).not.toHaveBeenCalled();
  });

  it('ignores an older response that arrives after a newer one', async () => {
    const first = deferred<Chat[]>();
    const second = deferred<Chat[]>();
    const responses = [first.promise, second.promise];
    const onLoaded = vi.fn();
    const onFailed = vi.fn();
    const refresh = createChatListLoader(() => responses.shift()!, { onLoaded, onFailed });

    const older = refresh();
    const newer = refresh();
    second.resolve([chat('new')]);
    await newer;
    first.reject(new Error('late failure'));
    await older;

    expect(onLoaded).toHaveBeenCalledTimes(1);
    expect(onLoaded).toHaveBeenCalledWith([chat('new')]);
    expect(onFailed).not.toHaveBeenCalled();
  });
});
