import React, { useState } from 'react';
import { X, Copy, Check, Share2, Globe } from 'lucide-react';
import type { Chat } from '../../types';

interface ShareModalProps {
  chat: Chat | null;
  isOpen: boolean;
  onClose: () => void;
}

export const ShareModal: React.FC<ShareModalProps> = ({ chat, isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !chat) return null;

  const shareUrl = `${window.location.origin}/#share=${chat.id}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700 shadow-2xl p-6 text-slate-100 relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-sap-600/20 border border-sap-500/30 text-sap-400 flex items-center justify-center">
            <Share2 className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Share link to chat</h2>
            <p className="text-xs text-slate-400">Share this SAP consultation session</p>
          </div>
        </div>

        {/* Chat Title Preview */}
        <div className="mb-4 p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center gap-2.5">
          <Globe className="w-4 h-4 text-sap-400 shrink-0" />
          <span className="text-xs font-medium text-slate-200 truncate">{chat.title}</span>
        </div>

        {/* Copy Link Input & Button */}
        <div className="mb-4">
          <label className="block text-xs font-semibold text-slate-400 mb-1.5">
            Public link to conversation
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={shareUrl}
              className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 font-mono focus:outline-none"
            />
            <button
              onClick={handleCopy}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition shrink-0 ${
                copied
                  ? 'bg-emerald-600 text-white'
                  : 'bg-sap-600 hover:bg-sap-500 text-white'
              }`}
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Link</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Footer Note */}
        <div className="pt-3 border-t border-slate-800 flex items-center gap-2 text-[11px] text-slate-500">
          <Globe className="w-3.5 h-3.5 text-orange-400 shrink-0" />
          <span>Anyone with this link will have view-only access to this conversation.</span>
        </div>
      </div>
    </div>
  );
};
