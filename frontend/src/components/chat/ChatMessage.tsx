import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Copy, Check, Eye, Layers, RotateCcw } from 'lucide-react';
import type { Message } from '../../types';
import { GroundingScoreBadge } from './GroundingScoreBadge';
import { SourceTypeBadge } from './SourceTypeBadge';
import { CitationModal } from './CitationModal';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamingStage?: string | null;
  onRetry?: () => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  isStreaming = false,
  streamingStage = null,
  onRetry,
}) => {
  const [copied, setCopied] = useState(false);
  const [showSourcesModal, setShowSourcesModal] = useState(false);

  const isUser = message.role === 'user';
  const hasCitations = !!(message.citations && message.citations.length > 0);
  const hasWebSources = !!(message.web_sources && message.web_sources.length > 0);
  const hasSources = !isUser && (hasCitations || hasWebSources);
  const sourceCount = (message.citations?.length || 0) + (message.web_sources?.length || 0);

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isInterrupted = message.source_type === 'interrupted' || message.source_type === 'error';

  return (
    <>
      <div className={`py-6 px-4 md:px-8 border-b border-slate-800/60 ${isUser ? 'bg-slate-900/30' : 'bg-slate-950/40'}`}>
        <div className="max-w-4xl mx-auto flex gap-4 items-start">
          {/* Avatar */}
          <div className="shrink-0 mt-0.5">
            {isUser ? (
              <div className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 font-semibold text-xs shadow-sm">
                <User className="w-4 h-4" />
              </div>
            ) : (
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-sap-700 via-sap-600 to-sap-400 flex items-center justify-center text-white shadow-md shadow-sap-600/30 border border-sap-400/40">
                <Layers className="w-4 h-4" />
              </div>
            )}
          </div>

          {/* Content Area */}
          <div className="flex-1 min-w-0">
            {/* Header info (role name + badges + action buttons) */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-200">
                  {isUser ? 'You' : 'SAP Knowledge Assistant'}
                </span>

                {!isUser && !isStreaming && (
                  <>
                    <SourceTypeBadge sourceType={message.source_type} />
                    <GroundingScoreBadge score={message.grounding_score} />
                  </>
                )}
              </div>

            <div className="flex items-center gap-1.5">
              {!isStreaming && message.content && (
                <button
                  onClick={handleCopy}
                  className="text-slate-500 hover:text-slate-300 transition p-1 rounded hover:bg-slate-800 text-xs flex items-center gap-1 cursor-pointer"
                  title="Copy response"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span className="hidden sm:inline">{copied ? 'Copied' : 'Copy'}</span>
                </button>
              )}
            </div>
          </div>

          {/* Body Content */}
          {isStreaming && !message.content ? (
            /* Minimal ChatGPT-style Thinking / Pipeline Status Indicator */
            <div className="flex items-center gap-2.5 py-1.5 text-slate-300 text-sm select-none">
              <span className="font-medium text-sap-400 animate-pulse">
                {streamingStage || 'Thinking...'}
              </span>
              <span className="inline-flex items-center gap-1">
                <span
                  className="w-1.5 h-1.5 rounded-full bg-sap-400 animate-bounce"
                  style={{ animationDuration: '0.9s', animationDelay: '0ms' }}
                />
                <span
                  className="w-1.5 h-1.5 rounded-full bg-sap-400 animate-bounce"
                  style={{ animationDuration: '0.9s', animationDelay: '180ms' }}
                />
                <span
                  className="w-1.5 h-1.5 rounded-full bg-sap-400 animate-bounce"
                  style={{ animationDuration: '0.9s', animationDelay: '360ms' }}
                />
              </span>
            </div>
          ) : (
            <div className="prose-sap text-sm text-slate-200 leading-relaxed break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ node, ...props }) => (
                    <div className="overflow-x-auto my-3 border border-slate-700/60 rounded-xl">
                      <table className="min-w-full divide-y divide-slate-700/60 text-left text-xs" {...props} />
                    </div>
                  ),
                  th: ({ node, ...props }) => (
                    <th className="px-3 py-2 bg-slate-800/80 font-semibold text-slate-200" {...props} />
                  ),
                  td: ({ node, ...props }) => (
                    <td className="px-3 py-2 border-t border-slate-800/60 text-slate-300" {...props} />
                  ),
                  pre: ({ node, ...props }) => (
                    <div className="overflow-x-auto rounded-xl bg-slate-950/80 p-3 my-2 border border-slate-800">
                      <pre {...props} />
                    </div>
                  ),
                  code: ({ node, className, children, ...props }) => {
                    const isInline = !className;
                    return isInline ? (
                      <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sap-300 font-mono text-[12px]" {...props}>
                        {children}
                      </code>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>

              {/* Streaming Cursor */}
              {isStreaming && (
                <span className="inline-block w-1.5 h-4 ml-0.5 bg-sap-400 animate-pulse align-middle rounded-xs" />
              )}
            </div>
          )}

          {/* Interrupted / Error retry banner */}
          {isInterrupted && (
            <div className="mt-3 p-3 rounded-xl bg-slate-900/80 border border-amber-500/30 text-xs text-slate-300 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-amber-300">
                <span>Generation interrupted.</span>
              </div>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 transition text-xs font-medium cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Retry</span>
                </button>
              )}
            </div>
          )}

          {/* Sources button below content */}
          {hasSources && !isStreaming && (
            <div className="mt-3.5 pt-2 flex items-center">
              <button
                onClick={() => setShowSourcesModal(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-850 text-slate-300 hover:text-sap-300 border border-slate-800 hover:border-sap-500/40 transition text-xs font-medium shadow-xs group cursor-pointer"
                title="Click to view all verified sources & citations"
              >
                <Eye className="w-3.5 h-3.5 text-sap-400 group-hover:scale-110 transition-transform" />
                <span>Sources ({sourceCount})</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>

    {/* Citation Detail Modal */}
    <CitationModal
      citations={message.citations}
      webSources={message.web_sources}
      isOpen={showSourcesModal}
      onClose={() => setShowSourcesModal(false)}
    />
  </>
);
};
