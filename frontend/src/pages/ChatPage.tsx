import React, { useState, useEffect, useRef } from 'react';
import { Menu, ChevronDown } from 'lucide-react';
import type { Chat, Message } from '../types';
import { Sidebar } from '../components/sidebar/Sidebar';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatInput } from '../components/chat/ChatInput';
import { WelcomeScreen } from '../components/chat/WelcomeScreen';
import {
  apiGetChats,
  apiCreateChat,
  apiUpdateChat,
  apiDeleteChat,
  apiGetMessages,
  apiStreamMessage,
  apiSavePartialMessage,
  type StreamMetadata,
  type StreamStatus,
} from '../services/api';

export const ChatPage: React.FC = () => {
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingStage, setStreamingStage] = useState<string | null>(null);
  const [streamingMeta, setStreamingMeta] = useState<StreamMetadata | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastUserPromptRef = useRef<string>('');

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  // Auto-scroll on content updates unless user has scrolled up
  useEffect(() => {
    if (!isUserScrolledUp) {
      scrollToBottom(streamingContent ? 'auto' : 'smooth');
    }
  }, [messages, streamingContent, streamingStage, isUserScrolledUp]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    // If more than 90px from bottom, pause auto-scroll
    setIsUserScrolledUp(distanceFromBottom > 90);
  };

  // Load chats on mount
  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    try {
      const data = await apiGetChats();
      setChats(data);
      if (data.length > 0 && !activeChatId) {
        selectChat(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load chats:', err);
    }
  };

  const selectChat = async (chatId: string) => {
    if (isLoading && abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsLoading(false);
    }
    setActiveChatId(chatId);
    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
    setIsUserScrolledUp(false);
    try {
      const msgs = await apiGetMessages(chatId);
      setMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages for chat:', chatId, err);
      setMessages([]);
    }
  };

  const handleNewChat = async () => {
    if (isLoading && abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsLoading(false);
    }
    try {
      const newChat = await apiCreateChat('New SAP Chat');
      setChats([newChat, ...chats]);
      setActiveChatId(newChat.id);
      setMessages([]);
      setStreamingContent(null);
      setStreamingStage(null);
      setStreamingMeta(null);
      setIsUserScrolledUp(false);
      setSidebarOpen(false);
    } catch (err) {
      console.error('Failed to create new chat:', err);
    }
  };

  const handleRenameChat = async (id: string, newTitle: string) => {
    try {
      const updated = await apiUpdateChat(id, newTitle);
      setChats(chats.map(c => (c.id === id ? updated : c)));
    } catch (err) {
      console.error('Failed to rename chat:', err);
    }
  };

  const handleDeleteChat = async (id: string) => {
    try {
      await apiDeleteChat(id);
      const remaining = chats.filter(c => c.id !== id);
      setChats(remaining);
      if (activeChatId === id) {
        if (remaining.length > 0) {
          selectChat(remaining[0].id);
        } else {
          setActiveChatId(null);
          setMessages([]);
        }
      }
    } catch (err) {
      console.error('Failed to delete chat:', err);
    }
  };

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
        chat_id: activeChatId || '',
        role: 'assistant',
        content: stoppedContent,
        source_type: 'interrupted',
        grounding_score: streamingMeta?.grounding_score,
        created_at: new Date().toISOString(),
        citations: streamingMeta?.citations || [],
        web_sources: streamingMeta?.web_sources || [],
      };

      setMessages(prev => [...prev, stoppedAssistantMsg]);

      if (activeChatId && stoppedContent.trim()) {
        apiSavePartialMessage(activeChatId, stoppedContent).catch(() => {});
      }
    }

    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
  };

  const handleSendMessage = async (content: string) => {
    let currentId = activeChatId;
    lastUserPromptRef.current = content;

    // If no active chat, create one automatically
    if (!currentId) {
      try {
        const newChat = await apiCreateChat(content.slice(0, 30));
        setChats([newChat, ...chats]);
        currentId = newChat.id;
        setActiveChatId(currentId);
      } catch (err) {
        console.error('Could not create initial chat:', err);
        return;
      }
    }

    // Optimistically add user message to UI
    const tempUserMsg: Message = {
      id: `user-${Date.now()}`,
      chat_id: currentId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      citations: [],
      web_sources: [],
    };

    setMessages(prev => [...prev, tempUserMsg]);
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
      currentId,
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
          const resolvedContent = finalText && finalText.length >= accumulatedText.length
            ? finalText
            : (accumulatedText || finalText || '');

          const finalAssistantMsg: Message = {
            id: effectiveMeta.message_id || `msg-${Date.now()}`,
            chat_id: currentId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: effectiveMeta.source_type || 'knowledge_base',
            grounding_score: effectiveMeta.grounding_score,
            created_at: new Date().toISOString(),
            citations: effectiveMeta.citations || [],
            web_sources: effectiveMeta.web_sources || [],
          };

          setMessages(prev => {
            if (prev.some(m => m.id === finalAssistantMsg.id)) {
              return prev.map(m => m.id === finalAssistantMsg.id ? finalAssistantMsg : m);
            }
            return [...prev, finalAssistantMsg];
          });

          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);

          // Refresh chat list to update titles and active states
          apiGetChats().then(setChats).catch(() => {});
        },
        onError: (err: any) => {
          console.error('Stream error:', err);
          setIsLoading(false);
          abortControllerRef.current = null;

          // Preserve partial text if any was generated
          const resolvedContent = accumulatedText.trim()
            ? accumulatedText
            : 'Generation interrupted. Please try again.';

          const errorMsg: Message = {
            id: `err-${Date.now()}`,
            chat_id: currentId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: 'error',
            grounding_score: streamMetaRef.grounding_score,
            created_at: new Date().toISOString(),
            citations: streamMetaRef.citations || [],
            web_sources: streamMetaRef.web_sources || [],
          };

          setMessages(prev => [...prev, errorMsg]);
          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);
        },
      },
      controller.signal
    );
  };

  const activeChat = chats.find(c => c.id === activeChatId);

  return (
    <div className="flex h-screen w-full bg-[#0b1120] text-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={(id) => {
          selectChat(id);
          setSidebarOpen(false);
        }}
        onNewChat={handleNewChat}
        onRenameChat={handleRenameChat}
        onDeleteChat={handleDeleteChat}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full min-w-0 bg-[#0f172a] relative">
        {/* Top Header Bar */}
        <header className="h-14 border-b border-slate-800/80 bg-slate-950/40 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-semibold text-slate-200 truncate">
                {activeChat ? activeChat.title : 'New SAP Session'}
              </span>
              <span className="hidden sm:inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sap-500/10 text-sap-400 border border-sap-500/20">
                SAP Scope Only
              </span>
            </div>
          </div>
        </header>

        {/* Message Area */}
        <div
          ref={messagesContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto flex flex-col relative scroll-smooth"
        >
          {messages.length === 0 && streamingContent === null ? (
            <WelcomeScreen onSelectPrompt={(prompt) => handleSendMessage(prompt)} />
          ) : (
            <div className="flex-1 pb-4">
              {messages.map((msg, idx) => {
                const isLast = idx === messages.length - 1;
                return (
                  <ChatMessage
                    key={msg.id}
                    message={msg}
                    onRetry={
                      isLast && (msg.source_type === 'error' || msg.source_type === 'interrupted')
                        ? () => handleSendMessage(lastUserPromptRef.current)
                        : undefined
                    }
                  />
                );
              })}

              {/* In-flight streaming response */}
              {streamingContent !== null && (
                <ChatMessage
                  message={{
                    id: 'streaming-assistant',
                    chat_id: activeChatId || '',
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
                scrollToBottom('smooth');
              }}
              className="sticky bottom-4 self-center z-20 flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-slate-800/95 hover:bg-slate-700 text-slate-200 border border-slate-700/80 shadow-xl text-xs font-medium transition cursor-pointer backdrop-blur-md hover:scale-105 active:scale-95"
            >
              <ChevronDown className="w-4 h-4 text-sap-400 animate-bounce" />
              <span>Jump to latest</span>
            </button>
          )}
        </div>

        {/* Bottom Input Area */}
        <ChatInput
          onSendMessage={handleSendMessage}
          onStop={handleStopGeneration}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
};
