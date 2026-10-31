import type { Message } from '../../types';

// Client-made ids: optimistic prompts, failed/stopped answers, and the in-flight stream.
const UNSTORED_ID = /^(user|err|stopped|msg|streaming)-/;

/** Only messages with a stored row can be edited, shared, rated or regenerated. */
export const isStoredMessage = (message: Message) => !UNSTORED_ID.test(message.id);

/** Plain text for read-aloud: drops markdown syntax and evidence markers like [E1]. */
export const toSpeechText = (markdown: string) =>
  markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\s?\[E\d{1,3}(?:\s*,\s*E\d{1,3})*\]/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s*\|?[\s:-]+\|[\s|:-]*$/gm, '')
    .replace(/[`*_#>|~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
