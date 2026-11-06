import { useEffect, useRef, useState } from 'react';
import type { Message, TokenSavingsSummary, TokenUsage } from '../../types';

/** Shown on hover: how the saving is estimated and what it is compared with. */
export const TOKEN_ESTIMATE_NOTE =
  'Estimated at about 4 characters per token. A typical AI chatbot resends the whole conversation and every ' +
  'matching passage with each question; Clyptus.AI sends only the best passages and a short summary.';

export const formatTokens = (tokens: number): string => Math.max(0, Math.round(tokens)).toLocaleString('en-US');

export const tokensLabel = (tokens: number): string =>
  `~${formatTokens(tokens)} ${Math.round(tokens) === 1 ? 'token' : 'tokens'}`;

/** The free tokens an answer cost: "0.5 tokens", "1 token", "0 tokens". */
export const formatTokenCost = (cost: number): string => {
  const rounded = Math.round(Math.max(0, cost) * 1000) / 1000;
  return `${rounded} ${rounded === 1 ? 'token' : 'tokens'}`;
};

export interface SavingsMessage {
  saved: boolean;
  emoji: string;
  title: string;
  detail: string;
}

/**
 * What the popup says after every answer: always a saving, never "none". The saving is the estimate against
 * a typical chatbot; when that estimate is not positive, it is the answer's cost in Clyptus tokens (the
 * 0 to 1 the user was charged) against the tokens the same question takes in a typical chatbot.
 */
export const savingsMessage = (usage: TokenUsage): SavingsMessage => {
  const baseline = Math.max(0, usage.baseline);
  const charged = typeof usage.cost === 'number' ? usage.cost : null;
  const saved = usage.saved > 0 ? usage.saved : charged !== null ? Math.max(0, Math.round(baseline - charged)) : 0;
  if (saved > 0) {
    const percent = baseline > 0 ? Math.min(99, Math.max(1, Math.round((saved / baseline) * 100))) : 0;
    return {
      saved: true,
      emoji: '😊',
      title: `You saved ${tokensLabel(saved)}! 🎉`,
      detail: percent
        ? `That's ${percent}% fewer tokens than other AI chatbots would use for this question, counted 1 token for 1 token. 😊`
        : 'Fewer tokens than other AI chatbots would use for this question, counted 1 token for 1 token. 😊',
    };
  }
  return {
    saved: true,
    emoji: '😊',
    title: 'You saved tokens on this answer! 🎉',
    detail: 'Clyptus.AI uses fewer tokens than other AI chatbots for the same question. 😊',
  };
};

/** Tokens saved by the answers in one chat (only answers with stored figures count). */
export const chatSavings = (messages: Message[]): number =>
  messages.reduce(
    (total, message) => total + (message.role === 'assistant' ? Math.max(0, message.token_usage?.saved ?? 0) : 0),
    0,
  );

/** The Settings total. Like the popup, a saving is never shown as 0. */
export const accountSavingsText = (summary: TokenSavingsSummary): { headline: string; detail: string } => {
  if (summary.saved <= 0) {
    return {
      headline: 'No tokens saved yet',
      detail: summary.answers > 0
        ? 'Savings grow as your conversations get longer.'
        : 'Your savings appear here after your first answers.',
    };
  }
  const percent = summary.baseline > 0 ? Math.max(1, Math.round((summary.saved / summary.baseline) * 100)) : 0;
  const answers = `${summary.answers} ${summary.answers === 1 ? 'answer' : 'answers'}`;
  return {
    headline: `${tokensLabel(summary.saved)} saved`,
    detail: percent
      ? `Across ${answers} · ${percent}% fewer tokens than other AI chatbots would use.`
      : `Across ${answers}.`,
  };
};

/** Counts smoothly from `initial` (then from the last shown value) to `target`, so the number runs up. */
export const useCountUp = (target: number, initial = target, durationMs = 900): number => {
  const [value, setValue] = useState(initial);
  const valueRef = useRef(initial);

  useEffect(() => {
    const from = valueRef.current;
    if (from === target) return;
    const start = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      const next = Math.round(from + (target - from) * (1 - (1 - progress) ** 3));
      valueRef.current = next;
      setValue(next);
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return value;
};
