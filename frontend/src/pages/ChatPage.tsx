import React, { useState, useEffect, useRef } from 'react';
import { Menu } from 'lucide-react';
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
  type StreamMetadata
} from '../services/api';

export const ChatPage: React.FC = () => {
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingMeta, setStreamingMeta] = useState<StreamMetadata | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

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
    setActiveChatId(chatId);
    setStreamingContent(null);
    setStreamingMeta(null);
    try {
      const msgs = await apiGetMessages(chatId);
      setMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages for chat:', chatId, err);
      setMessages([]);
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await apiCreateChat('New SAP Chat');
      setChats([newChat, ...chats]);
      setActiveChatId(newChat.id);
      setMessages([]);
      setStreamingContent(null);
      setStreamingMeta(null);
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

  const handleSendMessage = async (content: string) => {
    let currentId = activeChatId;

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
      id: `temp-${Date.now()}`,
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
    setStreamingMeta(null);

    // Stream response via SSE
    let accumulatedText = '';
    let streamMetaRef: StreamMetadata | null = null;

    await apiStreamMessage(
      currentId,
      content,
      (meta) => {
        streamMetaRef = meta;
        setStreamingMeta(meta);
      },
      (token) => {
        accumulatedText += token;
        setStreamingContent(accumulatedText);
      },
      (finalText?: string) => {
        // Streaming done
        setIsLoading(false);
        const resolvedContent = finalText && finalText.length >= accumulatedText.length ? finalText : (accumulatedText || finalText || '');
        const finalAssistantMsg: Message = {
          id: streamMetaRef?.message_id || `msg-${Date.now()}`,
          chat_id: currentId!,
          role: 'assistant',
          content: resolvedContent,
          source_type: streamMetaRef?.source_type || 'knowledge_base',
          grounding_score: streamMetaRef?.grounding_score,
          created_at: new Date().toISOString(),
          citations: streamMetaRef?.citations || [],
          web_sources: streamMetaRef?.web_sources || [],
        };
        setMessages(prev => {
          if (prev.some(m => m.id === finalAssistantMsg.id)) {
            return prev.map(m => m.id === finalAssistantMsg.id ? finalAssistantMsg : m);
          }
          return [...prev, finalAssistantMsg];
        });
        setStreamingContent(null);
        setStreamingMeta(null);
        // Refresh chat list to update titles/timestamps
        apiGetChats().then(setChats).catch(() => {});
      },
      (err) => {
        console.error('Stream error:', err);
        setIsLoading(false);
        setStreamingContent(null);
        const errorMsg: Message = {
          id: `err-${Date.now()}`,
          chat_id: currentId!,
          role: 'assistant',
          content: 'An error occurred while connecting to the SAP Knowledge Assistant. Please try again.',
          source_type: 'error',
          created_at: new Date().toISOString(),
          citations: [],
          web_sources: [],
        };
        setMessages(prev => [...prev, errorMsg]);
      }
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
              className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
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
        <div className="flex-1 overflow-y-auto flex flex-col">
          {messages.length === 0 && !streamingContent ? (
            <WelcomeScreen onSelectPrompt={(prompt) => handleSendMessage(prompt)} />
          ) : (
            <div className="flex-1 pb-4">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {/* In-flight streaming response indicator */}
              {streamingContent !== null && (
                <ChatMessage
                  message={{
                    id: 'streaming-assistant',
                    chat_id: activeChatId || '',
                    role: 'assistant',
                    content: streamingContent + ' ▍',
                    source_type: streamingMeta?.source_type,
                    grounding_score: streamingMeta?.grounding_score,
                    created_at: new Date().toISOString(),
                    citations: streamingMeta?.citations || [],
                    web_sources: streamingMeta?.web_sources || [],
                  }}
                />
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom Input Area */}
        <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
};
