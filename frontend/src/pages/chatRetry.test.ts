import { describe, expect, it } from 'vitest';
import type { DocumentAttachment, Message } from '../types';
import { retryRequestFor } from './chatRetry';

const message = (role: Message['role'], content: string, extra: Partial<Message> = {}): Message => ({
  id: `${role}-${content.slice(0, 8)}`,
  chat_id: 'chat-a',
  role,
  content,
  created_at: '2026-11-04T10:00:00',
  citations: [],
  web_sources: [],
  ...extra,
});

const pdf: DocumentAttachment = { name: 'spec.pdf', file_type: 'pdf', page_count: 3, text: 'Extracted text' };

describe('retryRequestFor: Retry resends the question before a failed or stopped answer', () => {
  it('resends the attachments with the question while their text is still in memory', () => {
    const messages = [
      message('user', '[Attached: spec.pdf (3 pages)]\n\nSummarise this spec', { attachments: [pdf] }),
      message('assistant', 'Generation interrupted.', { source_type: 'error' }),
    ];
    expect(retryRequestFor(messages, 1)).toEqual({ content: 'Summarise this spec', attachments: [pdf] });
  });

  it('resends only the text when the files are no longer available (loaded from the server)', () => {
    const messages = [
      message('user', '[Attached: spec.pdf (3 pages)]\n\nSummarise this spec', {
        attachments: [{ name: 'spec.pdf', file_type: 'pdf', page_count: 3 }],
      }),
      message('assistant', 'Partial', { source_type: 'interrupted' }),
    ];
    expect(retryRequestFor(messages, 1)).toEqual({ content: 'Summarise this spec' });
  });

  it('uses the question of this chat, after a page refresh as well', () => {
    const messages = [
      message('user', 'First question'),
      message('assistant', 'First answer'),
      message('user', 'Second question'),
      message('assistant', 'Partial', { source_type: 'interrupted' }),
    ];
    expect(retryRequestFor(messages, 3)).toEqual({ content: 'Second question' });
  });

  it('offers no retry without a question to resend', () => {
    expect(retryRequestFor([message('assistant', 'Error', { source_type: 'error' })], 0)).toBeNull();
    expect(retryRequestFor([message('user', '   '), message('assistant', 'Error', { source_type: 'error' })], 1)).toBeNull();
  });
});
