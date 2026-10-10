import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, Lock } from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import type { Message } from '../types';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatInput } from '../components/chat/ChatInput';
import { WelcomeScreen } from '../components/chat/WelcomeScreen';
import { AuthLimitModal } from '../components/chat/AuthLimitModal';
import { useAuth } from '../context/AuthContext';

import {
  apiCreateChat,
  apiGetMessages,
  apiStreamMessage,
  apiSavePartialMessage,
  type StreamMetadata,
  type StreamStatus,
} from '../services/api';

const GUEST_QUERY_LIMIT = 2;
const GUEST_COUNT_KEY = 'clyptus_trial_query_count';

export const ChatPage: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingStage, setStreamingStage] = useState<string | null>(null);
  const [streamingMeta, setStreamingMeta] = useState<StreamMetadata | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [trialCount, setTrialCount] = useState<number>(() => {
    try {
      return parseInt(localStorage.getItem(GUEST_COUNT_KEY) || '0', 10);
    } catch {
      return 0;
    }
  });

  const isTrialUser = !user || user.isGuest || user.email === 'consultant@clyptusap.ai';

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastUserPromptRef = useRef<string>('');
  const justCreatedChatIdRef = useRef<string | null>(null);

  const isAutoScrollingRef = useRef(false);

  const scrollToBottom = (instant = false) => {
    if (!messagesContainerRef.current) return;
    if (instant) {
      if (!isAutoScrollingRef.current) {
        isAutoScrollingRef.current = true;
        requestAnimationFrame(() => {
          if (messagesContainerRef.current) {
            messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
          }
          isAutoScrollingRef.current = false;
        });
      }
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Auto-scroll smoothly without jitter on content updates unless user has scrolled up
  useEffect(() => {
    if (!isUserScrolledUp) {
      scrollToBottom(!!streamingContent);
    }
  }, [messages, streamingContent, streamingStage, isUserScrolledUp]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    // If more than 90px from bottom, pause auto-scroll
    setIsUserScrolledUp(distanceFromBottom > 90);
  };

  // Load messages when conversationId changes
  useEffect(() => {
    if (conversationId && justCreatedChatIdRef.current === conversationId) {
      // Don't reset state if this navigation was triggered by creating a chat for the current stream
      justCreatedChatIdRef.current = null;
      return;
    }

    if (isLoading && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
    setIsUserScrolledUp(false);

    if (conversationId) {
      apiGetMessages(conversationId)
        .then(setMessages)
        .catch((err) => {
          console.error('Failed to load messages for chat:', conversationId, err);
          setMessages([]);
        });
    } else {
      setMessages([]);
    }
  }, [conversationId]);

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);

    // Preserve partially generated text in chat history and database
    if (streamingContent !== null) {
      const stoppedContent = streamingContent.trim() ? streamingContent : 'Generation stopped.';
      const stoppedAssistantMsg: Message = {
        id: streamingMeta?.message_id || `stopped-${Date.now()}`,
        chat_id: conversationId || '',
        role: 'assistant',
        content: stoppedContent,
        source_type: 'interrupted',
        grounding_score: streamingMeta?.grounding_score,
        created_at: new Date().toISOString(),
        citations: streamingMeta?.citations || [],
        web_sources: streamingMeta?.web_sources || [],
      };

      setMessages((prev) => [...prev, stoppedAssistantMsg]);

      if (conversationId && stoppedContent.trim()) {
        apiSavePartialMessage(conversationId, stoppedContent).catch(() => {});
      }
    }

    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
  };

  const handleSendMessage = async (content: string) => {
    // Check trial limit for free preview users
    if (isTrialUser && trialCount >= GUEST_QUERY_LIMIT) {
      setShowAuthModal(true);
      return;
    }

    if (isTrialUser) {
      const nextCount = trialCount + 1;
      setTrialCount(nextCount);
      localStorage.setItem(GUEST_COUNT_KEY, String(nextCount));
    }

    lastUserPromptRef.current = content;
    let targetChatId = conversationId;

    // If no active chat in route, create one and navigate
    if (!targetChatId) {
      try {
        const title = content.length > 35 ? content.slice(0, 35) + '...' : content;
        const newChat = await apiCreateChat(title);
        targetChatId = newChat.id;
        justCreatedChatIdRef.current = newChat.id;
        navigate(`/app/chat/${newChat.id}`, { replace: true });
      } catch (err) {
        console.error('Could not create initial chat:', err);
        return;
      }
    }

    // Optimistically add user message to UI
    const tempUserMsg: Message = {
      id: `user-${Date.now()}`,
      chat_id: targetChatId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      citations: [],
      web_sources: [],
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);
    setStreamingContent('');
    setStreamingStage('Thinking...');
    setStreamingMeta(null);
    setIsUserScrolledUp(false);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let accumulatedText = '';
    let streamMetaRef: StreamMetadata = {};

    await apiStreamMessage(
      targetChatId,
      content,
      {
        onStatus: (status: StreamStatus) => {
          setStreamingStage(status.message);
        },
        onMetadata: (meta: StreamMetadata) => {
          streamMetaRef = { ...streamMetaRef, ...meta };
          setStreamingMeta(streamMetaRef);
        },
        onToken: (token: string) => {
          accumulatedText += token;
          setStreamingContent(accumulatedText);
        },
        onDone: (doneMeta: StreamMetadata, finalText?: string) => {
          setIsLoading(false);
          abortControllerRef.current = null;
          const effectiveMeta = { ...streamMetaRef, ...doneMeta };
          const resolvedContent =
            finalText && finalText.trim().length > 0
              ? finalText
              : accumulatedText || '';

          const finalAssistantMsg: Message = {
            id: effectiveMeta.message_id || `msg-${Date.now()}`,
            chat_id: targetChatId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: effectiveMeta.source_type || 'knowledge_base',
            grounding_score: effectiveMeta.grounding_score,
            verification_status: effectiveMeta.verification_status,
            internal_evidence_confidence: effectiveMeta.internal_evidence_confidence,
            selected_evidence_quality: effectiveMeta.selected_evidence_quality,
            kb_score: effectiveMeta.kb_score,
            web_score: effectiveMeta.web_score,
            winning_score: effectiveMeta.winning_score,
            is_in_rag_pipeline: effectiveMeta.is_in_rag_pipeline,
            external_search_used: effectiveMeta.external_search_used,
            follow_up_questions: effectiveMeta.follow_up_questions || [],
            created_at: new Date().toISOString(),
            citations: effectiveMeta.citations || [],
            web_sources: effectiveMeta.web_sources || [],
          };

          setMessages((prev) => {
            if (prev.some((m) => m.id === finalAssistantMsg.id)) {
              return prev.map((m) => (m.id === finalAssistantMsg.id ? finalAssistantMsg : m));
            }
            return [...prev, finalAssistantMsg];
          });

          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);
        },
        onError: (err: any) => {
          console.error('Stream error:', err);
          setIsLoading(false);
          abortControllerRef.current = null;

          const resolvedContent = accumulatedText.trim()
            ? accumulatedText
            : 'Generation interrupted. Please try again.';

          const errorMsg: Message = {
            id: `err-${Date.now()}`,
            chat_id: targetChatId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: 'error',
            grounding_score: streamMetaRef.grounding_score,
            created_at: new Date().toISOString(),
            citations: streamMetaRef.citations || [],
            web_sources: streamMetaRef.web_sources || [],
          };

          setMessages((prev) => [...prev, errorMsg]);
          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);
        },
      },
      controller.signal
    );
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-52px)] min-w-0 bg-[#ffffff] dark:bg-[#000000] relative text-slate-800 dark:text-slate-100 font-sans transition-colors">
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto flex flex-col relative bg-[#ffffff] dark:bg-[#000000] transition-colors"
      >
        {messages.length === 0 && streamingContent === null ? (
          <div className="flex-1 flex items-center justify-center py-6">
            <WelcomeScreen onSelectPrompt={(prompt) => handleSendMessage(prompt)} />
          </div>
        ) : (
          <div className="flex-1 pb-4">
            {messages.map((msg, idx) => {
              const isLast = idx === messages.length - 1;
              return (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onSelectFollowUp={(q) => handleSendMessage(q)}
                  onRetry={
                    isLast && (msg.source_type === 'error' || msg.source_type === 'interrupted')
                      ? () => handleSendMessage(lastUserPromptRef.current)
                      : undefined
                  }
                />
              );
            })}

            {/* In-flight streaming response with ChatGPT thinking animation & streaming cursor */}
            {streamingContent !== null && (
              <ChatMessage
                message={{
                  id: 'streaming-assistant',
                  chat_id: conversationId || '',
                  role: 'assistant',
                  content: streamingContent,
                  source_type: streamingMeta?.source_type,
                  grounding_score: streamingMeta?.grounding_score,
                  created_at: new Date().toISOString(),
                  citations: streamingMeta?.citations || [],
                  web_sources: streamingMeta?.web_sources || [],
                }}
                isStreaming={true}
                streamingStage={streamingStage}
              />
            )}

            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Floating "Jump to latest" button when scrolled up */}
        {isUserScrolledUp && (
          <button
            onClick={() => {
              setIsUserScrolledUp(false);
              scrollToBottom(false);
            }}
            className="sticky bottom-4 self-center z-20 flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-white/95 dark:bg-slate-900/95 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 shadow-xl text-xs font-medium transition cursor-pointer backdrop-blur-md hover:scale-105 active:scale-95"
          >
            <ChevronDown className="w-4 h-4 text-orange-400 animate-bounce" />
            <span>Jump to latest</span>
          </button>
        )}
      </div>

      {/* Trial Preview Status Pill */}
      {isTrialUser && (
        <div className="w-full max-w-4xl mx-auto px-4 pt-1 flex items-center justify-center">
          {trialCount < GUEST_QUERY_LIMIT ? (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-50 dark:bg-[#0c0c12] border border-orange-200 dark:border-orange-500/25 text-[11px] text-orange-800 dark:text-orange-300 shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
              <span>Free Preview: <strong>{trialCount} of {GUEST_QUERY_LIMIT}</strong> questions used</span>
              <button
                type="button"
                onClick={() => navigate('/login?mode=register')}
                className="text-orange-600 dark:text-white hover:text-orange-700 dark:hover:text-orange-200 underline font-semibold ml-1 cursor-pointer"
              >
                Sign up for unlimited
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAuthModal(true)}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-orange-950/60 border border-orange-500/40 text-[11px] text-orange-200 hover:bg-orange-900/50 transition cursor-pointer shadow-md shadow-orange-500/10"
            >
              <Lock size={12} className="text-orange-400" />
              <span>Preview limit reached (2/2) · <strong>Sign in or Sign up to continue</strong></span>
            </button>
          )}
        </div>
      )}

      {/* Bottom Input Area */}
      <ChatInput
        onSendMessage={handleSendMessage}
        onStop={handleStopGeneration}
        isLoading={isLoading}
      />

      <AuthLimitModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        questionCount={trialCount}
      />
    </div>
  );
};

