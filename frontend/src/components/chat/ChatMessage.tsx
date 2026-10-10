import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Copy, Check, Eye, RotateCcw, Sparkles, ArrowRight } from 'lucide-react';
import type { Message } from '../../types';
import { GroundingScoreBadge } from './GroundingScoreBadge';
import { SourceTypeBadge } from './SourceTypeBadge';
import { CitationModal } from './CitationModal';
import iconOnly from '../../assets/clyptusap-icon.png';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamingStage?: string | null;
  onRetry?: () => void;
  onSelectFollowUp?: (question: string) => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  isStreaming = false,
  streamingStage = null,
  onRetry,
  onSelectFollowUp,
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
      <div className={`py-6 px-4 md:px-8 transition-colors ${isUser ? 'bg-[#fbfbf9] dark:bg-[#07070b] border-b border-[#e8e8e3] dark:border-[#14141e]' : 'bg-[#ffffff] dark:bg-[#000000] border-b border-[#ecece8] dark:border-[#101016]'}`}>
        <div className="max-w-4xl mx-auto flex gap-4 items-start">
          {/* Avatar */}
          <div className="shrink-0 mt-0.5">
            {isUser ? (
              <div className="w-8 h-8 rounded-xl bg-[#f0f0ec] dark:bg-[#12121a] border border-[#dcdcd6] dark:border-[#20202e] flex items-center justify-center text-slate-700 dark:text-slate-200 font-semibold text-xs shadow-sm">
                <User className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              </div>
            ) : (
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-orange-600 via-orange-500 to-orange-400 p-1 flex items-center justify-center text-white shadow-lg shadow-orange-500/25 border border-orange-400/50">
                <img src={iconOnly} alt="Clyptusap.ai" className="w-full h-full object-contain filter drop-shadow-sm" />
              </div>
            )}
          </div>

          {/* Content Area */}
          <div className="flex-1 min-w-0">
            {/* Header info (role name + badges + action buttons) */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {isUser ? 'You' : 'cClyptus.AI Assistant'}
                </span>

                {!isUser && !isStreaming && (
                  <>
                    <SourceTypeBadge sourceType={message.source_type} />
                    {message.source_type !== 'refusal' && (
                      <>
                        <GroundingScoreBadge
                          score={message.grounding_score}
                          verificationStatus={message.verification_status}
                        />
                        {/* KB Score vs Web Score comparison - shown when web was used */}
                        {message.external_search_used && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-100 dark:bg-cyan-950/80 text-cyan-800 dark:text-cyan-300 border border-cyan-300 dark:border-cyan-800/40">
                            🌐 Web: Used
                          </span>
                        )}
                        {/* Inline score comparison: KB vs Web score + winner */}
                        {(message.kb_score !== undefined || message.internal_evidence_confidence !== undefined || message.web_score !== undefined || message.selected_evidence_quality !== undefined) && (() => {
                          const kbVal = message.kb_score ?? message.internal_evidence_confidence ?? 0;
                          const webVal = message.web_score ?? message.selected_evidence_quality ?? 0;
                          const kbPct = Math.round(kbVal * 100);
                          const webPct = Math.round(webVal * 100);
                          const hasWeb = message.external_search_used || (message.web_score !== undefined && message.web_score > 0);
                          const kbWon = kbVal >= webVal;

                          return (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 dark:bg-slate-900/90 text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-slate-700/60 shadow-sm">
                              <span className="text-orange-600 dark:text-orange-400 font-semibold">KB:</span>
                              <span className="font-mono font-bold text-orange-600 dark:text-orange-300">{kbPct}%</span>
                              {hasWeb && (
                                <>
                                  <span className="text-slate-400 dark:text-slate-500 font-bold">vs</span>
                                  <span className="text-cyan-600 dark:text-cyan-400 font-semibold">Web:</span>
                                  <span className="font-mono font-bold text-cyan-700 dark:text-cyan-300">{webPct}%</span>
                                  <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                    kbWon 
                                      ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-700/50' 
                                      : 'bg-cyan-100 dark:bg-cyan-950/80 text-cyan-800 dark:text-cyan-300 border border-cyan-300 dark:border-cyan-700/50'
                                  }`}>
                                    {kbWon ? '🏆 KB Wins' : '🏆 Web Wins'}
                                  </span>
                                </>
                              )}
                            </span>
                          );
                        })()}
                      </>
                    )}
                  </>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                {!isStreaming && message.content && (
                  <button
                    onClick={handleCopy}
                    className="text-slate-400 hover:text-slate-700 dark:text-slate-500 dark:hover:text-slate-300 transition p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-xs flex items-center gap-1 cursor-pointer"
                    title="Copy response"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span className="hidden sm:inline">{copied ? 'Copied' : 'Copy'}</span>
                  </button>
                )}
              </div>
            </div>

            {/* Body Content */}
            {isStreaming && !message.content ? (
              /* Pipeline Status Indicator with Company Logo Orange Accents */
              <div className="flex items-center gap-2.5 py-1.5 text-slate-600 dark:text-slate-300 text-sm select-none">
                <span className="font-medium text-orange-500 dark:text-orange-400 animate-pulse">
                  {streamingStage || 'Thinking...'}
                </span>
                <span className="inline-flex items-center gap-1">
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '0ms' }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '180ms' }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '360ms' }}
                  />
                </span>
              </div>
            ) : (
              <div className="prose-sap text-sm text-slate-800 dark:text-slate-200 leading-relaxed break-words">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ node, ...props }) => (
                      <div className="overflow-x-auto my-3 border border-slate-200 dark:border-[#1e1e2c] rounded-xl bg-white dark:bg-[#08080c]">
                        <table className="min-w-full divide-y divide-slate-200 dark:divide-[#1e1e2c] text-left text-xs" {...props} />
                      </div>
                    ),
                    th: ({ node, ...props }) => (
                      <th className="px-3 py-2 bg-slate-100 dark:bg-[#0e0e16] font-semibold text-slate-800 dark:text-slate-100 border-b border-slate-200 dark:border-[#1e1e2c]" {...props} />
                    ),
                    td: ({ node, ...props }) => (
                      <td className="px-3 py-2 border-t border-slate-100 dark:border-[#161622] text-slate-700 dark:text-slate-300" {...props} />
                    ),
                    pre: ({ node, ...props }) => (
                      <div className="overflow-x-auto rounded-xl bg-slate-50 dark:bg-[#06060a] p-3.5 my-2 border border-slate-200 dark:border-[#1c1c28]">
                        <pre {...props} />
                      </div>
                    ),
                    code: ({ node, className, children, ...props }) => {
                      const isInline = !className;
                      return isInline ? (
                        <code className="px-1.5 py-0.5 rounded bg-orange-50 dark:bg-[#0f0f18] text-orange-600 dark:text-orange-400 font-mono text-[12px] border border-orange-200 dark:border-orange-500/25" {...props}>
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
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-orange-500 animate-pulse align-middle rounded-xs" />
                )}
              </div>
            )}

            {/* Interrupted / Error retry banner */}
            {isInterrupted && (
              <div className="mt-3 p-3 rounded-xl bg-amber-50 dark:bg-slate-900/90 border border-amber-300 dark:border-amber-500/30 text-xs text-amber-900 dark:text-slate-300 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300">
                  <span>Generation interrupted.</span>
                </div>
                {onRetry && (
                  <button
                    onClick={onRetry}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-100 dark:bg-amber-500/10 hover:bg-amber-200 dark:hover:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30 transition text-xs font-medium cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Retry</span>
                  </button>
                )}
              </div>
            )}

            {/* Sources button below content */}
            {hasSources && !isStreaming && (
              <div className="mt-3.5 pt-2 flex items-center gap-2">
                <button
                  onClick={() => setShowSourcesModal(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-900/90 hover:bg-slate-200 dark:hover:bg-slate-850 text-slate-700 dark:text-slate-300 hover:text-orange-600 dark:hover:text-orange-400 border border-slate-200 dark:border-slate-800 hover:border-orange-300 dark:hover:border-orange-500/40 transition text-xs font-medium shadow-xs group cursor-pointer"
                  title="Click to view all verified sources & citations"
                >
                  <Eye className="w-3.5 h-3.5 text-orange-500 group-hover:scale-110 transition-transform" />
                  <span>Sources ({sourceCount})</span>
                </button>
              </div>
            )}

            {/* Recommended Follow-up Questions (Exactly 3) */}
            {!isStreaming && message.source_type !== 'refusal' && message.follow_up_questions && message.follow_up_questions.length > 0 && (
              <div className="mt-5 pt-3.5 border-t border-slate-200 dark:border-[#181824]">
                <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-orange-500 dark:text-orange-400" />
                  <span>Recommended follow-up questions</span>
                </div>
                <div className="flex flex-col sm:flex-row flex-wrap gap-2">
                  {message.follow_up_questions.map((fq, idx) => (
                    <button
                      key={idx}
                      onClick={() => onSelectFollowUp?.(fq)}
                      className="text-left text-xs px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#0b0b12] hover:bg-orange-50/70 dark:hover:bg-[#141420] text-slate-800 dark:text-slate-200 hover:text-orange-600 dark:hover:text-orange-400 border border-slate-200 dark:border-[#1e1e2c] hover:border-orange-300 dark:hover:border-orange-500/40 transition-all cursor-pointer shadow-xs group flex items-center justify-between gap-2.5"
                    >
                      <span>{fq}</span>
                      <ArrowRight className="w-3 h-3 text-slate-400 dark:text-slate-500 group-hover:text-orange-500 dark:group-hover:text-orange-400 group-hover:translate-x-0.5 transition-all shrink-0" />
                    </button>
                  ))}
                </div>
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
