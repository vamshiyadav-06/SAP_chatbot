import React, { useState, useMemo, useEffect } from 'react';
import { Plus, Search, Layers, LogOut, Shield, ChevronLeft, Pin, Archive, ChevronDown, ChevronRight } from 'lucide-react';
import type { Chat } from '../../types';
import { ChatListItem } from './ChatListItem';
import { ShareModal } from '../chat/ShareModal';
import { useAuth } from '../../context/AuthContext';
import { userStorageKey } from '../../services/userStorage';

interface SidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onRenameChat: (id: string, newTitle: string) => void;
  onDeleteChat: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onRenameChat,
  onDeleteChat,
  isOpen,
  onToggle,
}) => {
  const { user, logout } = useAuth();
  const [search, setSearch] = useState('');
  const [shareChat, setShareChat] = useState<Chat | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [showPinned, setShowPinned] = useState(true);

  // Persistent Pinned Chats in localStorage
  const [pinnedIds, setPinnedIds] = useState<string[]>([]);
  const [archivedIds, setArchivedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!user?.id) {
      setPinnedIds([]);
      setArchivedIds([]);
      return;
    }
    try {
      setPinnedIds(JSON.parse(localStorage.getItem(userStorageKey(user.id, 'pinned_chats')) || '[]'));
    } catch {
      setPinnedIds([]);
    }
    try {
      setArchivedIds(JSON.parse(localStorage.getItem(userStorageKey(user.id, 'archived_chats')) || '[]'));
    } catch {
      setArchivedIds([]);
    }
  }, [user?.id]);

  const togglePin = (id: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      if (user?.id) localStorage.setItem(userStorageKey(user.id, 'pinned_chats'), JSON.stringify(next));
      return next;
    });
  };

  const toggleArchive = (id: string) => {
    setArchivedIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      if (user?.id) localStorage.setItem(userStorageKey(user.id, 'archived_chats'), JSON.stringify(next));
      return next;
    });
  };

  const filteredChats = useMemo(() => {
    if (!search.trim()) return chats;
    return chats.filter((c) => c.title.toLowerCase().includes(search.toLowerCase()));
  }, [chats, search]);

  const { pinnedChats, normalChats, archivedChats } = useMemo(() => {
    const pinned: Chat[] = [];
    const normal: Chat[] = [];
    const archived: Chat[] = [];

    filteredChats.forEach((chat) => {
      if (archivedIds.includes(chat.id)) {
        archived.push(chat);
      } else if (pinnedIds.includes(chat.id)) {
        pinned.push(chat);
      } else {
        normal.push(chat);
      }
    });

    return { pinnedChats: pinned, normalChats: normal, archivedChats: archived };
  }, [filteredChats, pinnedIds, archivedIds]);

  const groupedChats = useMemo(() => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const last7Days = new Date(today);
    last7Days.setDate(last7Days.getDate() - 7);

    const groups: { [key: string]: Chat[] } = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: [],
    };

    normalChats.forEach((chat) => {
      const chatDate = new Date(chat.updated_at);
      if (chatDate.toDateString() === today.toDateString()) {
        groups['Today'].push(chat);
      } else if (chatDate.toDateString() === yesterday.toDateString()) {
        groups['Yesterday'].push(chat);
      } else if (chatDate >= last7Days) {
        groups['Previous 7 Days'].push(chat);
      } else {
        groups['Older'].push(chat);
      }
    });

    return groups;
  }, [normalChats]);

  return (
    <>
      {isOpen && (
        <div
          onClick={onToggle}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs md:hidden"
        />
      )}

      <aside
        className={`fixed md:static inset-y-0 left-0 z-40 w-72 bg-slate-950 border-r border-slate-800 flex flex-col transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-sap-700 via-sap-600 to-sap-400 flex items-center justify-center text-white shadow-md shadow-sap-600/30 border border-sap-400/30">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold tracking-tight text-white block">SAP Assistant</span>
              <span className="text-[10px] text-slate-400 flex items-center gap-1 font-medium">
                <Shield className="w-2.5 h-2.5 text-sap-400" />
                Enterprise RAG
              </span>
            </div>
          </div>

          <button
            onClick={onToggle}
            className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        {/* New SAP Chat Button */}
        <div className="p-3">
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-sap-600/20 hover:bg-sap-600/30 text-sap-300 border border-sap-500/40 font-semibold text-xs transition duration-150 shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>New SAP Chat</span>
          </button>
        </div>

        {/* Search */}
        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search chats..."
              className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sap-500/60"
            />
          </div>
        </div>

        {/* Chat List */}
        <div className="flex-1 overflow-y-auto px-2 space-y-4 py-2">
          {/* Pinned Section */}
          {pinnedChats.length > 0 && (
            <div>
              <button
                onClick={() => setShowPinned((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider text-sap-400 hover:bg-slate-900 transition group"
              >
                <div className="flex items-center gap-1.5">
                  <Pin className="w-3 h-3 text-sap-400" />
                  <span>Pinned</span>
                </div>
                <ChevronDown
                  className={`w-3.5 h-3.5 text-slate-500 transition-transform duration-200 ${showPinned ? 'rotate-0' : '-rotate-90'}`}
                />
              </button>
              {showPinned && (
              <div className="space-y-0.5 mt-0.5">
                {pinnedChats.map((chat) => (
                  <ChatListItem
                    key={chat.id}
                    chat={chat}
                    isActive={chat.id === activeChatId}
                    isPinned={true}
                    isArchived={false}
                    onSelect={onSelectChat}
                    onRename={onRenameChat}
                    onDelete={onDeleteChat}
                    onShare={(c) => setShareChat(c)}
                    onTogglePin={togglePin}
                    onToggleArchive={toggleArchive}
                  />
                ))}
              </div>
              )}
            </div>
          )}


          {/* Regular Date-grouped Sections */}
          {Object.entries(groupedChats).map(([groupName, groupChats]) => {
            if (groupChats.length === 0) return null;
            return (
              <div key={groupName}>
                <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  {groupName}
                </div>
                <div className="space-y-0.5">
                  {groupChats.map((chat) => (
                    <ChatListItem
                      key={chat.id}
                      chat={chat}
                      isActive={chat.id === activeChatId}
                      isPinned={false}
                      isArchived={false}
                      onSelect={onSelectChat}
                      onRename={onRenameChat}
                      onDelete={onDeleteChat}
                      onShare={(c) => setShareChat(c)}
                      onTogglePin={togglePin}
                      onToggleArchive={toggleArchive}
                    />
                  ))}
                </div>
              </div>
            );
          })}

          {/* Archived Section */}
          {archivedChats.length > 0 && (
            <div className="pt-2 border-t border-slate-850">
              <button
                onClick={() => setShowArchived(!showArchived)}
                className="w-full flex items-center justify-between px-3 py-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-900 rounded-lg transition"
              >
                <div className="flex items-center gap-1.5">
                  <Archive className="w-3.5 h-3.5 text-slate-400" />
                  <span>Archived ({archivedChats.length})</span>
                </div>
                {showArchived ? (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                )}
              </button>

              {showArchived && (
                <div className="space-y-0.5 mt-1">
                  {archivedChats.map((chat) => (
                    <ChatListItem
                      key={chat.id}
                      chat={chat}
                      isActive={chat.id === activeChatId}
                      isPinned={false}
                      isArchived={true}
                      onSelect={onSelectChat}
                      onRename={onRenameChat}
                      onDelete={onDeleteChat}
                      onShare={(c) => setShareChat(c)}
                      onTogglePin={togglePin}
                      onToggleArchive={toggleArchive}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {filteredChats.length === 0 && (
            <div className="text-center py-8 px-4 text-xs text-slate-500">
              {search ? 'No chats found matching search.' : 'No recent chats yet.'}
            </div>
          )}
        </div>

        {/* User Footer */}
        {user && (
          <div className="p-3 border-t border-slate-800 bg-slate-950/80">
            <div className="flex items-center justify-between p-2 rounded-xl bg-slate-900/60 border border-slate-800/80">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-7 h-7 rounded-lg bg-sap-600/30 border border-sap-500/40 text-sap-300 flex items-center justify-center font-bold text-xs shrink-0">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-slate-200 block truncate leading-tight">
                    {user.name}
                  </span>
                  <span className="text-[10px] text-slate-400 block truncate">
                    {user.email}
                  </span>
                </div>
              </div>

              <button
                onClick={logout}
                className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition"
                title="Log Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </aside>

      {/* Share Modal */}
      <ShareModal
        chat={shareChat}
        isOpen={!!shareChat}
        onClose={() => setShareChat(null)}
      />
    </>
  );
};
