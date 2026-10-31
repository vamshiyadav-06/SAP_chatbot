import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import type { Message, DocumentAttachment } from '../types';
import { ChatMessage } from '../components/chat/ChatMessage';
import { isStoredMessage } from '../components/chat/messageUtils';
import { ChatInput } from '../components/chat/ChatInput';
import { WelcomeScreen } from '../components/chat/WelcomeScreen';

import {
  apiCreateChat,
  apiGetMessages,
  apiStreamMessage,
  apiEditMessageStream,
  apiSavePartialMessage,
  type StreamCallbacks,
  type StreamMetadata,
  type StreamStatus,
} from '../services/api';


export const ChatPage: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  // A prompt opened from a share link pre-fills the input; the user decides whether to send it.
  const [prefillPrompt] = useState<string>(() => (location.state as { prefillPrompt?: string } | null)?.prefillPrompt ?? '');

  useEffect(() => {
    // Drop the router state so a page refresh doesn't pre-fill again.
    if (prefillPrompt) navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingStage, setStreamingStage] = useState<string | null>(null);
  const [streamingMeta, setStreamingMeta] = useState<StreamMetadata | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  // Server-issued id of the running stream; required to save a stopped answer.
  const streamIdRef = useRef<string | null>(null);
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

  // Prevent browser from navigating to file/folder when dropped outside the dropzone
  useEffect(() => {
    const handleWindowDragOver = (e: DragEvent) => e.preventDefault();
    const handleWindowDrop = (e: DragEvent) => e.preventDefault();

    window.addEventListener('dragover', handleWindowDragOver);
    window.addEventListener('drop', handleWindowDrop);
    return () => {
      window.removeEventListener('dragover', handleWindowDragOver);
      window.removeEventListener('drop', handleWindowDrop);
    };
  }, []);

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

  // Load messages when conversationId changes.
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

  const accumulatedTargetRef = useRef<string>('');
  const displayedTextRef = useRef<string>('');
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingDoneRef = useRef<{
    meta: StreamMetadata;
    finalText?: string;
    targetChatId: string;
  } | null>(null);

  // Clean up streaming ticker interval on unmount
  useEffect(() => {
    return () => {
      if (tickerRef.current) {
        clearInterval(tickerRef.current);
        tickerRef.current = null;
      }
    };
  }, []);

  const handleStopGeneration = () => {
    if (tickerRef.current) {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
    pendingDoneRef.current = null;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);

    // Preserve partially generated text in chat history and database (registered users only)
    const currentStream = displayedTextRef.current || streamingContent;
    if (currentStream !== null) {
      const stoppedContent = currentStream.trim() ? currentStream : 'Generation stopped.';
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
        images: streamingMeta?.images || [],
      };

      setMessages((prev) => [...prev, stoppedAssistantMsg]);

      if (conversationId && stoppedContent.trim() && streamIdRef.current) {
        apiSavePartialMessage(conversationId, stoppedContent, streamIdRef.current).catch(() => {});
      }
    }

    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
  };

  const handleSendMessage = async (content: string, attachments?: DocumentAttachment[]) => {
    // One answer streams at a time; a second stream would share the reveal ticker and refs.
    if (isLoading) return;

    lastUserPromptRef.current = content;
    let targetChatId = conversationId;

    const displayContent =
      attachments && attachments.length > 0 && !content.startsWith('[Attached')
        ? `[Attached: ${attachments.map((a) => `${a.name} (${a.page_count || 1} pages)`).join(', ')}]\n\n${content}`
        : content;

    // Show the prompt before any request, so a failure below can never make it disappear.
    const tempUserMsg: Message = {
      id: `user-${Date.now()}`,
      chat_id: targetChatId || '',
      role: 'user',
      content: displayContent,
      attachments,
      created_at: new Date().toISOString(),
      citations: [],
      web_sources: [],
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    await streamAnswer(
      () => targetChatId || '',
      tempUserMsg.id,
      attachments && attachments.length > 0 ? 'Analyzing attached document(s)...' : 'Thinking...',
      async (callbacks, signal) => {
        // A first question starts a chat; failures are shown in the chat by streamAnswer.
        if (!targetChatId) {
          const title = content.length > 35 ? content.slice(0, 35) + '...' : content;
          let newChat;
          try {
            newChat = await apiCreateChat(title);
          } catch (err) {
            throw err;
          }
          targetChatId = newChat.id;
          setMessages((prev) => prev.map((m) => (m.id === tempUserMsg.id ? { ...m, chat_id: newChat.id } : m)));
          justCreatedChatIdRef.current = newChat.id;
          navigate(`/app/chat/${newChat.id}`, { replace: true });
          if (signal.aborted) return;
        }
        await apiStreamMessage(targetChatId, content, callbacks, signal, attachments);
      }
    );
  };

  // Rewrites a sent prompt: everything after it is discarded and a new answer is streamed.
  const handleEditMessage = async (messageId: string, newText: string) => {
    const text = newText.trim();
    const targetChatId = conversationId;
    if (!text || isLoading || !targetChatId) return;

    lastUserPromptRef.current = text;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === messageId);
      if (idx === -1) return prev;
      const original = prev[idx];
      // Files attached to the original prompt stay attached (the backend keeps them too).
      const attachedPrefix = original.content.match(/^\[Attached:\s*.+?\]\n\n/)?.[0] ?? '';
      return [...prev.slice(0, idx), { ...original, content: attachedPrefix + text }];
    });

    await streamAnswer(() => targetChatId, messageId, 'Thinking...', (callbacks, signal) =>
      apiEditMessageStream(targetChatId, messageId, text, callbacks, signal)
    );
  };

  // Drives the typewriter reveal for one answer stream and adds the finished answer to the chat.
  const streamAnswer = async (
    // A getter because a first question only gets its chat id once `start` has created the chat.
    getChatId: () => string,
    userMessageId: string,
    initialStage: string,
    start: (callbacks: StreamCallbacks, signal: AbortSignal) => Promise<void>
  ) => {
    setIsLoading(true);
    setStreamingContent('');
    setStreamingStage(initialStage);
    setStreamingMeta(null);
    setIsUserScrolledUp(false);

    accumulatedTargetRef.current = '';
    displayedTextRef.current = '';
    pendingDoneRef.current = null;
    if (tickerRef.current) {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }

    // Smooth progressive typewriter / token reveal ticker (ChatGPT feel)
    tickerRef.current = setInterval(() => {
      const target = accumulatedTargetRef.current;
      const current = displayedTextRef.current;

      if (current.length < target.length) {
        const diff = target.length - current.length;
        // Dynamic pacing: smooth character/word reveal without stalling
        const step = diff > 120 ? Math.ceil(diff / 4) : diff > 40 ? 6 : diff > 15 ? 3 : diff > 4 ? 2 : 1;
        const nextText = target.slice(0, current.length + step);
        displayedTextRef.current = nextText;
        setStreamingContent(nextText);
      } else if (pendingDoneRef.current) {
        // Stream completed from backend and all characters have smoothly appeared
        if (tickerRef.current) {
          clearInterval(tickerRef.current);
          tickerRef.current = null;
        }

        const { meta, finalText, targetChatId: finalChatId } = pendingDoneRef.current;
        pendingDoneRef.current = null;
        setIsLoading(false);
        abortControllerRef.current = null;

        const resolvedContent =
          finalText && finalText.trim().length > 0
            ? finalText
            : displayedTextRef.current || target || '';

        const finalAssistantMsg: Message = {
          id: meta.message_id || `msg-${Date.now()}`,
          chat_id: finalChatId,
          role: 'assistant',
          content: resolvedContent,
          source_type: meta.source_type || 'knowledge_base',
          grounding_score: meta.grounding_score,
          verification_status: meta.verification_status,
          internal_evidence_confidence: meta.internal_evidence_confidence,
          selected_evidence_quality: meta.selected_evidence_quality,
          kb_score: meta.kb_score,
          web_score: meta.web_score,
          winning_score: meta.winning_score,
          source_scores: meta.source_scores,
          is_in_rag_pipeline: meta.is_in_rag_pipeline,
          external_search_used: meta.external_search_used,
          follow_up_questions: meta.follow_up_questions || [],
          created_at: new Date().toISOString(),
          citations: meta.citations || [],
          web_sources: meta.web_sources || [],
          images: meta.images || [],
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
      }
    }, 20);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    streamIdRef.current = null;

    let streamMetaRef: StreamMetadata = {};

    const callbacks: StreamCallbacks = {
      onStreamId: (streamId: string) => {
        streamIdRef.current = streamId;
      },
      onUserMessage: (storedId: string) => {
        // Swap the optimistic id for the stored one so this prompt can be edited later.
        setMessages((prev) => prev.map((m) => (m.id === userMessageId ? { ...m, id: storedId } : m)));
      },
      onStatus: (status: StreamStatus) => {
        setStreamingStage(status.message);
      },
      onMetadata: (meta: StreamMetadata) => {
        streamMetaRef = { ...streamMetaRef, ...meta };
        setStreamingMeta(streamMetaRef);
      },
      onToken: (token: string) => {
        accumulatedTargetRef.current += token;
      },
      onDone: (doneMeta: StreamMetadata, finalText?: string) => {
        const effectiveMeta = { ...streamMetaRef, ...doneMeta };
        if (finalText && finalText.length > accumulatedTargetRef.current.length) {
          accumulatedTargetRef.current = finalText;
        }
        pendingDoneRef.current = {
          meta: effectiveMeta,
          finalText,
          targetChatId: getChatId(),
        };
      },
      onError: (err: any) => {
        console.error('Stream error:', err);
        if (tickerRef.current) {
          clearInterval(tickerRef.current);
          tickerRef.current = null;
        }
        pendingDoneRef.current = null;
        setIsLoading(false);
        abortControllerRef.current = null;

        // Keep whatever answer text arrived; otherwise say why there is none.
        const resolvedContent =
          accumulatedTargetRef.current.trim() ||
          displayedTextRef.current.trim() ||
          (err instanceof Error && err.message) ||
          'Generation interrupted. Please try again.';

        const errorMsg: Message = {
          id: `err-${Date.now()}`,
          chat_id: getChatId(),
          role: 'assistant',
          content: resolvedContent,
          source_type: 'error',
          grounding_score: streamMetaRef.grounding_score,
          created_at: new Date().toISOString(),
          citations: streamMetaRef.citations || [],
          web_sources: streamMetaRef.web_sources || [],
          images: streamMetaRef.images || [],
        };

        setMessages((prev) => [...prev, errorMsg]);
        setStreamingContent(null);
        setStreamingStage(null);
        setStreamingMeta(null);
      },
    };

    try {
      await start(callbacks, controller.signal);
    } catch (err) {
      // Anything `start` throws (e.g. the chat could not be created) must not leave the chat loading.
      if (!controller.signal.aborted) callbacks.onError?.(err);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full min-h-0 min-w-0 bg-[#ffffff] dark:bg-[#000000] relative text-slate-800 dark:text-slate-100 font-sans transition-colors overflow-hidden">
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
              // Regenerating re-runs the question before the latest answer through the edit flow.
              const question = idx > 0 ? messages[idx - 1] : undefined;
              const canRegenerate =
                isLast && msg.role === 'assistant' && question?.role === 'user' && isStoredMessage(question);
              return (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onSelectFollowUp={(q) => handleSendMessage(q)}
                  onEdit={
                    msg.role === 'user' && isStoredMessage(msg)
                      ? (text) => handleEditMessage(msg.id, text)
                      : undefined
                  }
                  editDisabled={isLoading}
                  onRegenerate={
                    canRegenerate
                      ? () => handleEditMessage(question!.id, question!.content.replace(/^\[Attached:\s*.+?\]\n\n/, ''))
                      : undefined
                  }
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
                  images: streamingMeta?.images || [],
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

      {/* Bottom Input Area */}
      <ChatInput
        onSendMessage={handleSendMessage}
        onStop={handleStopGeneration}
        isLoading={isLoading}
        initialInput={prefillPrompt}
      />

    </div>
  );
};

