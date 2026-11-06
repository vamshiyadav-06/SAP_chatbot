import type { DocumentAttachment, Message } from '../types';

// The "[Attached: …]" line the chat puts in front of a prompt sent with files.
const ATTACHED_PREFIX = /^\[Attached:\s*.+?\]\n\n/;

export interface RetryRequest {
  content: string;
  attachments?: DocumentAttachment[];
}

/**
 * What Retry under the answer at `answerIndex` sends again: the question before it, with its files when
 * their extracted text is still in memory (files of prompts loaded from the server have no text and cannot
 * be resent). Null when there is nothing to resend.
 */
export function retryRequestFor(messages: Message[], answerIndex: number): RetryRequest | null {
  let question: Message | undefined;
  for (let index = answerIndex - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') {
      question = messages[index];
      break;
    }
  }
  if (!question) return null;

  const content = question.content.replace(ATTACHED_PREFIX, '').trim();
  const attachments = (question.attachments ?? []).filter((attachment) => Boolean(attachment.text?.trim()));
  if (!content && attachments.length === 0) return null;
  return attachments.length > 0 ? { content, attachments } : { content };
}
