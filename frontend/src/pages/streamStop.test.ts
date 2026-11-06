import { describe, expect, it, vi } from 'vitest';
import { createStreamStopper } from './streamStop';

const setup = (chatId = 'chat-a') => {
  const save = vi.fn();
  const abort = vi.fn();
  const stopper = createStreamStopper({ getChatId: () => chatId, save, abort });
  return { stopper, save, abort };
};

describe('createStreamStopper: Stop always cancels the answer on the server', () => {
  it('saves the partial answer with the stream id and aborts when the id is already known', () => {
    const { stopper, save, abort } = setup();
    stopper.beginSend();
    stopper.setStreamId('stream-1');

    stopper.requestStop('Partial answer');

    expect(save).toHaveBeenCalledWith('chat-a', 'Partial answer', 'stream-1');
    expect(abort).toHaveBeenCalledOnce();
  });

  it('remembers a Stop pressed before the stream id arrives and cancels as soon as it does', () => {
    const { stopper, save, abort } = setup();
    stopper.beginSend();

    stopper.requestStop('Generation stopped.');
    // The request stays open: aborting now would lose the stream id needed to cancel on the server.
    expect(save).not.toHaveBeenCalled();
    expect(abort).not.toHaveBeenCalled();
    expect(stopper.stopRequested).toBe(true);

    stopper.setStreamId('stream-1');
    expect(save).toHaveBeenCalledWith('chat-a', 'Generation stopped.', 'stream-1');
    expect(abort).toHaveBeenCalledOnce();

    stopper.setStreamId('stream-1');
    stopper.requestStop('again');
    expect(save).toHaveBeenCalledOnce();
    expect(abort).toHaveBeenCalledOnce();
  });

  it('aborts at once when Stop comes before the question was sent, and the question is then not sent', () => {
    const { stopper, save, abort } = setup();

    stopper.requestStop('Generation stopped.');

    expect(abort).toHaveBeenCalledOnce();
    expect(stopper.beginSend()).toBe(false);
    expect(save).not.toHaveBeenCalled();
  });

  it('lets the question be sent when nobody pressed Stop', () => {
    const { stopper, save, abort } = setup();
    expect(stopper.beginSend()).toBe(true);
    stopper.setStreamId('stream-1');
    expect(save).not.toHaveBeenCalled();
    expect(abort).not.toHaveBeenCalled();
  });

  it('only aborts when the chat id is not known yet (nothing can be saved)', () => {
    const { stopper, save, abort } = setup('');
    stopper.beginSend();
    stopper.requestStop('Generation stopped.');
    stopper.setStreamId('stream-1');
    expect(save).not.toHaveBeenCalled();
    expect(abort).toHaveBeenCalledOnce();
  });

  it('saves a placeholder when nothing of the answer was shown yet', () => {
    const { stopper, save } = setup();
    stopper.beginSend();
    stopper.setStreamId('stream-1');
    stopper.requestStop('   ');
    expect(save).toHaveBeenCalledWith('chat-a', 'Generation stopped.', 'stream-1');
  });
});
