import React, { useEffect, useState } from 'react';
import { X, Globe, Link2, Check, Loader2 } from 'lucide-react';
import { apiSharePrompt } from '../../services/api';

interface SharePromptModalProps {
  chatId: string;
  messageId: string;
  prompt: string;
  /** Sharing an answer: the link shows the question and this answer. */
  isAnswer?: boolean;
  onClose: () => void;
}

const XLogo = () => (
  <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor" aria-hidden="true">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

const LinkedInLogo = () => (
  <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor" aria-hidden="true">
    <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z" />
  </svg>
);

const RedditLogo = () => (
  <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor" aria-hidden="true">
    <path d="M24 11.78a2.6 2.6 0 0 0-4.41-1.87 12.8 12.8 0 0 0-6.93-2.19l1.18-5.55 3.85.82a1.84 1.84 0 1 0 .19-.9l-4.3-.91a.46.46 0 0 0-.55.35l-1.32 6.19a12.86 12.86 0 0 0-7.03 2.19 2.6 2.6 0 1 0-2.87 4.26 5.1 5.1 0 0 0-.06.79c0 4.02 4.68 7.28 10.45 7.28s10.45-3.26 10.45-7.28c0-.26-.02-.53-.06-.79A2.6 2.6 0 0 0 24 11.78zM6.02 13.6a1.84 1.84 0 1 1 3.68 0 1.84 1.84 0 0 1-3.68 0zm10.31 4.87c-1.26 1.26-3.67 1.36-4.38 1.36s-3.12-.1-4.38-1.36a.48.48 0 0 1 .68-.68c.8.8 2.5 1.08 3.7 1.08 1.2 0 2.9-.28 3.7-1.08a.48.48 0 0 1 .68.68zm-.33-3.03a1.84 1.84 0 1 1 0-3.68 1.84 1.84 0 0 1 0 3.68z" />
  </svg>
);

export const SharePromptModal: React.FC<SharePromptModalProps> = ({ chatId, messageId, prompt, isAnswer = false, onClose }) => {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);

  // The public link is created only when the user opens this dialog.
  useEffect(() => {
    let cancelled = false;
    apiSharePrompt(chatId, messageId)
      .then((token) => !cancelled && setShareUrl(`${window.location.origin}/share/${token}`))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [chatId, messageId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const copyLink = async () => {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openShare = (buildUrl: (url: string) => string) => {
    if (shareUrl) window.open(buildUrl(shareUrl), '_blank', 'noopener,noreferrer');
  };

  const title = isAnswer ? 'SAP answer on Clyptus.AI' : 'SAP question on Clyptus.AI';
  const noun = isAnswer ? 'response' : 'prompt';
  const targets = [
    { label: 'X', icon: <XLogo />, href: (u: string) => `https://x.com/intent/tweet?url=${encodeURIComponent(u)}&text=${encodeURIComponent(title)}` },
    { label: 'LinkedIn', icon: <LinkedInLogo />, href: (u: string) => `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(u)}` },
    { label: 'Reddit', icon: <RedditLogo />, href: (u: string) => `https://www.reddit.com/submit?url=${encodeURIComponent(u)}&title=${encodeURIComponent(title)}` },
  ];

  const circleClass =
    'w-12 h-12 rounded-full flex items-center justify-center bg-slate-100 dark:bg-[#1a1a26] text-slate-800 dark:text-slate-100 group-hover:bg-slate-200 dark:group-hover:bg-[#242434] transition';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 dark:bg-black/70 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-prompt-title"
        className="w-full max-w-xl rounded-2xl bg-white dark:bg-[#0d0d14] border border-slate-200 dark:border-[#1e1e2c] shadow-2xl text-slate-800 dark:text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <h2 id="share-prompt-title" className="text-lg font-semibold">Share {noun}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-800 transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Prompt preview, faded at the bottom like a snapshot card */}
        <div className="mx-6 rounded-2xl border border-slate-200 dark:border-[#1e1e2c] bg-white dark:bg-[#08080c] p-4">
          <div className={`relative max-h-64 overflow-hidden flex ${isAnswer ? 'justify-start' : 'justify-end'}`}>
            <div className={`text-sm leading-relaxed whitespace-pre-wrap break-words ${isAnswer ? '' : 'max-w-[80%] rounded-2xl px-4 py-2.5 bg-slate-100 dark:bg-[#161622]'}`}>
              {prompt}
            </div>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-white dark:from-[#08080c] to-transparent" />
          </div>
        </div>

        <div className="px-6 pt-5 flex items-center gap-2 text-sm font-semibold">
          <Globe className="w-4 h-4" />
          <span>Share a public link to this {noun}</span>
        </div>
        <p className="px-6 pt-2 text-xs text-slate-500 dark:text-slate-400">
          Anyone with this link can read the shared prompt and answer. Attachments and internal sources are excluded.
        </p>
        {error && (
          <p className="px-6 pt-2 text-xs text-red-600 dark:text-red-400">Could not create a link. Please try again.</p>
        )}

        <div className="mt-4 border-t border-slate-200 dark:border-[#1e1e2c] px-6 py-5 flex justify-center gap-10 sm:gap-14">
          <button
            type="button"
            onClick={copyLink}
            disabled={!shareUrl}
            className="group flex flex-col items-center gap-2 text-xs cursor-pointer disabled:cursor-wait disabled:opacity-60"
          >
            <span className={circleClass}>
              {!shareUrl && !error ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : copied ? (
                <Check className="w-5 h-5 text-emerald-500" />
              ) : (
                <Link2 className="w-5 h-5" />
              )}
            </span>
            <span>{copied ? 'Copied' : 'Copy link'}</span>
          </button>
          {targets.map((t) => (
            <button
              key={t.label}
              type="button"
              onClick={() => openShare(t.href)}
              disabled={!shareUrl}
              className="group flex flex-col items-center gap-2 text-xs cursor-pointer disabled:cursor-wait disabled:opacity-60"
            >
              <span className={circleClass}>{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
