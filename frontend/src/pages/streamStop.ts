// Stop for the answer stream on screen. The server keeps generating (and saves the answer) even when the
// browser disconnects; only "save partial" with the stream id it sent first cancels it. Stop can be pressed
// before that id has arrived, so the request is kept open until it does.

const STOPPED_PLACEHOLDER = 'Generation stopped.';

export interface StreamStopper {
  /** Called right before the question is sent; false means Stop was already pressed, so do not send. */
  beginSend(): boolean;
  /** The server's stream id arrived; a Stop pressed before it is carried out now. */
  setStreamId(streamId: string): void;
  /** Stop pressed. `content` is what the user saw of the answer, saved as the stopped answer. */
  requestStop(content: string): void;
  readonly stopRequested: boolean;
}

interface StreamStopperDeps {
  /** The chat of this stream; empty while a first question is still creating its chat. */
  getChatId: () => string;
  save: (chatId: string, content: string, streamId: string) => void;
  abort: () => void;
}

export function createStreamStopper({ getChatId, save, abort }: StreamStopperDeps): StreamStopper {
  let sent = false;
  let streamId: string | null = null;
  let stopContent: string | null = null;
  let done = false;

  const cancel = () => {
    if (done || stopContent === null) return;
    done = true;
    const chatId = getChatId();
    if (chatId && streamId) save(chatId, stopContent.trim() ? stopContent : STOPPED_PLACEHOLDER, streamId);
    abort();
  };

  return {
    beginSend() {
      if (stopContent !== null) return false;
      sent = true;
      return true;
    },
    setStreamId(id: string) {
      streamId = id;
      cancel();
    },
    requestStop(content: string) {
      if (stopContent !== null) return;
      stopContent = content;
      // Nothing reached the server yet, or the id is known: cancel now. Otherwise wait for the id.
      if (!sent || streamId) cancel();
    },
    get stopRequested() {
      return stopContent !== null;
    },
  };
}
