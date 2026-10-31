import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiCreateChat, apiGetChats, setUnauthorizedHandler, streamSSE, type StreamCallbacks } from './api';

const sse = (...events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');

/** A response whose body delivers `chunks` and then closes. */
const streamResponse = (chunks: string[], status = 200) => {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } });
};

/** A fetch that never answers but rejects like the real one when its signal aborts. */
const hangingFetch = (_url: string, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  });

const recorder = () => {
  const calls = { done: [] as unknown[][], error: [] as Error[], tokens: [] as string[] };
  const callbacks: StreamCallbacks = {
    onDone: (...args) => calls.done.push(args),
    onError: (err) => calls.error.push(err),
    onToken: (t) => calls.tokens.push(t),
  };
  return { calls, callbacks };
};

beforeEach(() => {
  const store = new Map<string, string>([['sap_assistant_token', 'test-token']]);
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('streamSSE', () => {
  it('hands the server-issued stream id to the caller (needed to save a stopped answer)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
      sse({ type: 'stream', stream_id: 'signed-stream-id' }, { type: 'token', content: 'Hi' }),
      sse({ type: 'done', answer: 'Hi', message_id: 'a1' }),
    ])));
    const { calls, callbacks } = recorder();
    const ids: string[] = [];

    await streamSSE('/x', {}, { ...callbacks, onStreamId: (id) => ids.push(id) });

    expect(ids).toEqual(['signed-stream-id']);
    expect(calls.tokens.join('')).toBe('Hi');
  });

  it('delivers tokens and finishes once on a normal answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
      sse({ type: 'user_message', message_id: 'm1' }, { type: 'status', stage: 'thinking', message: 'Thinking...' }),
      sse({ type: 'token', content: 'Hello ' }, { type: 'token', content: 'world' }),
      sse({ type: 'done', answer: 'Hello world', message_id: 'a1' }),
    ])));
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.tokens.join('')).toBe('Hello world');
    expect(calls.done).toHaveLength(1);
    expect(calls.done[0][1]).toBe('Hello world');
    expect(calls.error).toHaveLength(0);
  });

  it('reports a backend error event once and never finishes as an answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
      sse({ type: 'token', content: 'Part' }, { type: 'error', message: 'Generation interrupted. Please try again.' }),
    ])));
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.error.map((e) => e.message)).toEqual(['Generation interrupted. Please try again.']);
    expect(calls.done).toHaveLength(0);
  });

  it('reports a stream that closes without a done event', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([sse({ type: 'token', content: 'Half an ans' })])));
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.done).toHaveLength(0);
    expect(calls.error).toHaveLength(1);
    expect(calls.error[0].message).toMatch(/cut off/);
  });

  it('survives malformed SSE lines', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
      'data: {not json\n\n',
      sse({ type: 'done', answer: 'ok' }),
    ])));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.done).toHaveLength(1);
    expect(calls.error).toHaveLength(0);
  });

  it('says the session expired on HTTP 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"Could not validate credentials"}', { status: 401 })));
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.error).toHaveLength(1);
    expect(calls.error[0]).toBeInstanceOf(ApiError);
    expect((calls.error[0] as ApiError).status).toBe(401);
    expect(calls.error[0].message).toMatch(/session has expired/);
  });

  it('says the server is unreachable when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const { calls, callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);

    expect(calls.error).toHaveLength(1);
    expect(calls.error[0].message).toMatch(/Cannot reach the server/);
  });

  it('gives up on a server that never responds', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(hangingFetch));
    const { calls, callbacks } = recorder();

    const run = streamSSE('/x', {}, callbacks);
    await vi.advanceTimersByTimeAsync(30_000);
    await run;

    expect(calls.error).toHaveLength(1);
    expect(calls.error[0].message).toMatch(/stopped responding/);
    expect(calls.done).toHaveLength(0);
  });

  it('ends silently when the user stops generation', async () => {
    vi.stubGlobal('fetch', vi.fn(hangingFetch));
    vi.spyOn(console, 'log').mockImplementation(() => {});
    const { calls, callbacks } = recorder();
    const controller = new AbortController();

    const run = streamSSE('/x', {}, callbacks, controller.signal);
    controller.abort();
    await run;

    expect(calls.error).toHaveLength(0);
    expect(calls.done).toHaveLength(0);
  });
});

describe('apiCreateChat', () => {
  it('throws a session-expired ApiError on HTTP 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));

    const err = await apiCreateChat('q').catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).toMatch(/session has expired/);
  });

  it('throws a readable error when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));

    await expect(apiCreateChat('q')).rejects.toThrow(/Cannot reach the server/);
  });
});

describe('expired sessions', () => {
  afterEach(() => setUnauthorizedHandler(null));

  it('a 401 on an authenticated request calls the global handler once per request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(apiGetChats()).rejects.toBeTruthy();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('a 401 on a request without a token (e.g. a wrong password) does not', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(apiGetChats()).rejects.toBeTruthy();
    expect(handler).not.toHaveBeenCalled();
  });

  it('a 401 on the answer stream reports the expired session too', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const { callbacks } = recorder();

    await streamSSE('/x', {}, callbacks);
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
