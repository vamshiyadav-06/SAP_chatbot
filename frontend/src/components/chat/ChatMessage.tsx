import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  User, Copy, Check, Eye, RotateCcw, Sparkles, ArrowRight, FileText, Share, Pencil,
  ThumbsUp, ThumbsDown, Volume2, Square, RefreshCw,
} from 'lucide-react';
import type { Message, MessageFeedback } from '../../types';
import { GroundingScoreBadge } from './GroundingScoreBadge';
import { SourceTypeBadge } from './SourceTypeBadge';
import { CitationModal } from './CitationModal';
import { SharePromptModal } from './SharePromptModal';
import { isStoredMessage, toSpeechText } from './messageUtils';
import { useAuth } from '../../context/AuthContext';
import { apiSetFeedback } from '../../services/api';
import iconOnly from '../../assets/clyptusap-icon.png';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamingStage?: string | null;
  onRetry?: () => void;
  onSelectFollowUp?: (question: string) => void;
  /** Present only for prompts that can be rewritten; called with the new prompt text. */
  onEdit?: (newText: string) => void;
  /** True while an answer is streaming, so a second request cannot start. */
  editDisabled?: boolean;
  /** Present only on the latest answer; asks the same question again for a new answer. */
  onRegenerate?: () => void;
}

const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window;

// Chrome stops speaking long utterances after ~15s, so text is queued in sentence-sized pieces.
const speechChunks = (text: string, max = 200): string[] => {
  const chunks: string[] = [];
  let current = '';
  for (const sentence of text.match(/[^.!?]+[.!?]*\s*/g) ?? [text]) {
    if (current && (current + sentence).length > max) {
      chunks.push(current.trim());
      current = '';
    }
    current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
};

const promptActionClass =
  'p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:text-slate-500 dark:hover:text-slate-200 dark:hover:bg-slate-800 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent';

const parseUserMessageContent = (content: string) => {
  const match = content.match(/^\[Attached:\s*(.+?)\]\n\n([\s\S]*)$/);
  if (match) {
    const rawList = match[1].split(', ');
    const attachments = rawList.map((item) => {
      const pageMatch = item.match(/^(.*?)\s*\((\d+)\s*pages?\)$/i);
      if (pageMatch) {
        return { name: pageMatch[1].trim(), details: `${pageMatch[2]} pages` };
      }
      return { name: item.trim(), details: '' };
    });
    return { attachments, text: match[2] };
  }
  return { attachments: null, text: content };
};

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  isStreaming = false,
  streamingStage = null,
  onRetry,
  onSelectFollowUp,
  onEdit,
  editDisabled = false,
  onRegenerate,
}) => {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<MessageFeedback | null>(message.feedback ?? null);
  const [speaking, setSpeaking] = useState(false);
  // Identifies this message's speech so a newer utterance elsewhere does not reset our state early.
  const speechRunRef = useRef(0);
  const [showShare, setShowShare] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [showSourcesModal, setShowSourcesModal] = useState(false);
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);

  const isUser = message.role === 'user';
  const { attachments: parsedAttachments, text: cleanUserContent } = isUser
    ? parseUserMessageContent(message.content)
    : { attachments: null, text: message.content };

  const effectiveAttachments = message.attachments && message.attachments.length > 0
    ? message.attachments.map((a) => ({ name: a.name, details: a.page_count ? `${a.page_count} pages` : '' }))
    : parsedAttachments;

  const displayContent = isUser ? cleanUserContent : message.content;

  const hasCitations = !!(message.citations && message.citations.length > 0);
  const hasWebSources = !!(message.web_sources && message.web_sources.length > 0);
  const hasSources = !isUser && (hasCitations || hasWebSources);
  const sourceCount = (message.citations?.length || 0) + (message.web_sources?.length || 0);

  // A prompt copies without its "[Attached: …]" prefix; an answer copies as-is.
  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(displayContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Clicking the active thumb clears it; the choice is rolled back if saving fails.
  const handleFeedback = (value: MessageFeedback) => {
    const previous = feedback;
    const next = previous === value ? null : value;
    setFeedback(next);
    apiSetFeedback(message.chat_id, message.id, next).catch(() => setFeedback(previous));
  };

  const stopSpeaking = () => {
    speechRunRef.current += 1;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  const toggleSpeak = () => {
    if (speaking) {
      stopSpeaking();
      return;
    }
    const chunks = speechChunks(toSpeechText(displayContent));
    if (chunks.length === 0) return;
    window.speechSynthesis.cancel(); // only one answer reads at a time
    const run = ++speechRunRef.current;
    chunks.forEach((chunk, i) => {
      const utterance = new SpeechSynthesisUtterance(chunk);
      const finish = () => {
        if (speechRunRef.current === run) setSpeaking(false);
      };
      utterance.onerror = finish;
      if (i === chunks.length - 1) utterance.onend = finish;
      window.speechSynthesis.speak(utterance);
    });
    setSpeaking(true);
  };

  // Stop reading if this answer leaves the screen (chat switch, regenerate, delete).
  const speakingRef = useRef(false);
  speakingRef.current = speaking;
  useEffect(() => {
    return () => {
      if (speakingRef.current) window.speechSynthesis.cancel();
    };
  }, []);

  const startEditing = () => {
    setDraft(displayContent);
    setIsEditing(true);
  };

  const submitEdit = () => {
    const text = draft.trim();
    if (!text || editDisabled) return;
    setIsEditing(false);
    if (text !== displayContent.trim()) onEdit?.(text);
  };

  const isInterrupted = message.source_type === 'interrupted' || message.source_type === 'error';

  return (
    <>
      <div className={`py-6 px-4 md:px-8 transition-colors ${isUser ? 'bg-[#fbfbf9] dark:bg-[#07070b] border-b border-[#e8e8e3] dark:border-[#14141e]' : 'bg-[#ffffff] dark:bg-[#000000] border-b border-[#ecece8] dark:border-[#101016]'}`}>
        <div className={`max-w-4xl mx-auto flex gap-4 items-start ${isUser ? 'flex-row-reverse' : ''}`}>
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
          <div className={`flex-1 min-w-0 ${isUser ? 'flex flex-col items-end' : ''}`}>
            {/* Header info (role name + badges + action buttons) */}
            <div className={`flex items-center mb-2 ${isUser ? 'flex-row-reverse gap-3' : 'justify-between'}`}>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {isUser ? 'You' : 'Clyptus.AI'}
                </span>

                {!isUser && !isStreaming && isAdmin && (
                  <>
                    <SourceTypeBadge sourceType={message.source_type} />
                    {message.source_type !== 'refusal' && message.source_type !== 'conversational' && (
                      <>
                        <GroundingScoreBadge
                          score={message.grounding_score}
                          verificationStatus={message.verification_status}
                        />
                        {message.external_search_used && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-100 dark:bg-cyan-950/80 text-cyan-800 dark:text-cyan-300 border border-cyan-300 dark:border-cyan-800/40">
                            🌐 External sources checked
                          </span>
                        )}
                        {message.source_scores && Object.keys(message.source_scores).length > 0 && (
                          <span className="inline-flex items-center gap-2 flex-wrap px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-slate-900/90 text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-slate-700/60 shadow-sm">
                            {Object.entries(message.source_scores).map(([source, score]) => (
                              <span key={source} className={source === message.source_type ? 'font-bold text-emerald-700 dark:text-emerald-300' : 'text-slate-500 dark:text-slate-400'}>
                                {source === message.source_type ? '🏆 ' : ''}{source.replaceAll('_', ' ')} {Math.round(score * 100)}%
                              </span>
                            ))}
                            {message.winning_score !== undefined && (
                              <span className="border-l border-slate-300 dark:border-slate-700 pl-2 font-semibold">selected score {Math.round(message.winning_score * 100)}%</span>
                            )}
                          </span>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>

            </div>

            {/* Body Content */}
            {isUser && isEditing ? (
              <div className="w-full max-w-[85%] rounded-2xl px-3 py-2.5 bg-white dark:bg-[#0b0b12] border border-orange-300 dark:border-orange-500/40 shadow-sm">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      submitEdit();
                    } else if (e.key === 'Escape') {
                      setIsEditing(false);
                    }
                  }}
                  autoFocus
                  rows={Math.min(8, Math.max(2, draft.split('\n').length))}
                  aria-label="Edit your question"
                  className="w-full resize-y bg-transparent text-sm text-slate-800 dark:text-slate-200 leading-relaxed outline-none"
                />
                <div className="mt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={submitEdit}
                    disabled={!draft.trim() || editDisabled}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-orange-500 hover:bg-orange-600 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Send
                  </button>
                </div>
              </div>
            ) : isStreaming && !message.content ? (
              /* Pipeline Status Indicator with Company Logo Orange Accents */
              <div className="flex items-center gap-2.5 py-1.5 text-slate-600 dark:text-slate-300 text-sm select-none">
                <span className="font-medium text-orange-500 dark:text-orange-400 animate-pulse">
                  {isAdmin ? (streamingStage || 'Thinking...') : 'Thinking...'}
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
              <div className={`prose-sap text-sm text-slate-800 dark:text-slate-200 leading-relaxed break-words ${isUser ? 'max-w-[85%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-orange-50/80 dark:bg-[#13131d] border border-orange-200/70 dark:border-orange-500/20' : ''}`}>
                {isUser && effectiveAttachments && effectiveAttachments.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3 not-prose">
                    {effectiveAttachments.map((att, idx) => (
                      <div
                        key={idx}
                        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-orange-50/90 dark:bg-[#13131d] border border-orange-200 dark:border-orange-500/30 text-xs text-orange-950 dark:text-orange-200 shadow-xs"
                      >
                        <span className="p-1 rounded-lg bg-orange-100 dark:bg-orange-500/20 text-orange-600 dark:text-orange-400">
                          <FileText className="w-3.5 h-3.5" />
                        </span>
                        <span className="font-semibold">{att.name}</span>
                        {att.details && <span className="text-[10px] text-slate-500 dark:text-slate-400">({att.details})</span>}
                      </div>
                    ))}
                  </div>
                )}

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
                  {displayContent}
                </ReactMarkdown>

                {/* Streaming Cursor */}
                {isStreaming && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-orange-500 animate-pulse align-middle rounded-xs" />
                )}
              </div>
            )}

            {/* Prompt actions: copy, share, edit */}
            {isUser && !isEditing && displayContent && (
              <div className="mt-1.5 flex items-center gap-0.5">
                <button type="button" onClick={handleCopy} className={promptActionClass} title={copied ? 'Copied' : 'Copy prompt'} aria-label="Copy prompt">
                  {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                </button>
                {isStoredMessage(message) && (
                  <button type="button" onClick={() => setShowShare(true)} className={promptActionClass} title="Share prompt" aria-label="Share prompt">
                    <Share className="w-4 h-4" />
                  </button>
                )}
                {onEdit && (
                  <button
                    type="button"
                    onClick={startEditing}
                    disabled={editDisabled}
                    className={promptActionClass}
                    title={editDisabled ? 'Wait for the current answer to finish' : 'Edit prompt'}
                    aria-label="Edit prompt"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                )}
              </div>
            )}

            {/* Answer actions: copy, rate, read aloud, share, regenerate */}
            {!isUser && !isStreaming && displayContent && (
              <div className="mt-3 flex items-center gap-0.5">
                <button type="button" onClick={handleCopy} className={promptActionClass} title={copied ? 'Copied' : 'Copy'} aria-label="Copy response">
                  {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                </button>
                {isStoredMessage(message) && (
                  <>
                    <button
                      type="button"
                      onClick={() => handleFeedback('up')}
                      className={promptActionClass}
                      title="Good response"
                      aria-label="Good response"
                      aria-pressed={feedback === 'up'}
                    >
                      <ThumbsUp className={`w-4 h-4 ${feedback === 'up' ? 'text-slate-800 dark:text-slate-100' : ''}`} fill={feedback === 'up' ? 'currentColor' : 'none'} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleFeedback('down')}
                      className={promptActionClass}
                      title="Bad response"
                      aria-label="Bad response"
                      aria-pressed={feedback === 'down'}
                    >
                      <ThumbsDown className={`w-4 h-4 ${feedback === 'down' ? 'text-slate-800 dark:text-slate-100' : ''}`} fill={feedback === 'down' ? 'currentColor' : 'none'} />
                    </button>
                  </>
                )}
                {canSpeak && (
                  <button
                    type="button"
                    onClick={toggleSpeak}
                    className={promptActionClass}
                    title={speaking ? 'Stop reading' : 'Read aloud'}
                    aria-label={speaking ? 'Stop reading' : 'Read aloud'}
                  >
                    {speaking ? <Square className="w-4 h-4" fill="currentColor" /> : <Volume2 className="w-4 h-4" />}
                  </button>
                )}
                {isStoredMessage(message) && (
                  <button type="button" onClick={() => setShowShare(true)} className={promptActionClass} title="Share response" aria-label="Share response">
                    <Share className="w-4 h-4" />
                  </button>
                )}
                {onRegenerate && (
                  <button
                    type="button"
                    onClick={() => {
                      if (speaking) stopSpeaking();
                      onRegenerate();
                    }}
                    disabled={editDisabled}
                    className={promptActionClass}
                    title={editDisabled ? 'Wait for the current answer to finish' : 'Regenerate response'}
                    aria-label="Regenerate response"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
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

            {/* Sources button below content - strictly restricted to administrator */}
            {!isUser && !isStreaming && isAdmin && message.source_type !== 'refusal' && (
              <div className="mt-3.5 pt-2 flex items-center gap-2">
                <button
                  onClick={() => setShowSourcesModal(true)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl transition text-xs font-medium shadow-xs group cursor-pointer ${
                    hasSources
                      ? 'bg-orange-50/90 dark:bg-[#12121e] hover:bg-orange-100 dark:hover:bg-[#1a1a2c] text-orange-950 dark:text-orange-200 border border-orange-200 dark:border-orange-500/35 hover:border-orange-400 dark:hover:border-orange-500/60'
                      : 'bg-slate-100 dark:bg-slate-900/70 hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800'
                  }`}
                  title="Admin Only: View internal sources & citations"
                >
                  <Eye className="w-3.5 h-3.5 text-orange-500 group-hover:scale-110 transition-transform" />
                  <span className="font-semibold">Sources ({sourceCount})</span>
                  {hasCitations && (
                    <span className="px-1.5 py-0.2 rounded bg-orange-200/70 dark:bg-orange-950/80 text-[10px] text-orange-800 dark:text-orange-300 font-mono font-bold">
                      {message.citations!.length} KB
                    </span>
                  )}
                  {hasWebSources && (
                    <span className="px-1.5 py-0.2 rounded bg-cyan-200/70 dark:bg-cyan-950/80 text-[10px] text-cyan-800 dark:text-cyan-300 font-mono font-bold">
                      {message.web_sources!.length} Web
                    </span>
                  )}
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

      {showShare && (
        <SharePromptModal
          chatId={message.chat_id}
          messageId={message.id}
          prompt={displayContent}
          isAnswer={!isUser}
          onClose={() => setShowShare(false)}
        />
      )}

      {/* Citation Detail Modal - only rendered for admin */}
      {isAdmin && (
        <CitationModal
          citations={message.citations}
          webSources={message.web_sources}
          isOpen={showSourcesModal}
          onClose={() => setShowSourcesModal(false)}
        />
      )}
    </>
  );
};
