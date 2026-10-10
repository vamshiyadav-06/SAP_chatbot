import React, { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  FolderPlus,
  LogOut,
  Menu,
  MessageSquarePlus,
  Pin,
  PinOff,
  Search,
  Settings2,
  UserRound,
  X,
  ChevronDown,
  CircleHelp,
  Trash2,
} from 'lucide-react';
import { BrandLogo } from '../components/navbar/BrandLogo';
import { ProjectModal } from '../components/projects/ProjectModal';
import { AssistantGuideModal } from '../components/ui/AssistantGuideModal';
import { useAuth } from '../context/AuthContext';
import { apiGetChats, apiCreateChat, apiDeleteChat } from '../services/api';
import { projectService } from '../services/projectService';
import type { Chat, Project } from '../types';

function dateGroup(chat: Chat): string {
  const date = new Date(chat.updated_at || chat.created_at);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return 'Today';
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return 'Earlier';
}

const PINNED_CHATS_KEY = 'clyptus_pinned_chats';

export const AppLayout: React.FC = () => {
  const [query, setQuery] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [helpModalOpen, setHelpModalOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [chats, setChats] = useState<Chat[]>([]);
  const [chatsLoading, setChatsLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>(() => projectService.getProjects());
  const [pinnedChatIds, setPinnedChatIds] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(PINNED_CHATS_KEY) || '[]');
    } catch {
      return [];
    }
  });

  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const isConversation = location.pathname === '/app' || location.pathname.includes('/chat/');

  // Refresh chats list
  const refreshChats = async () => {
    try {
      const data = await apiGetChats();
      setChats(data);
    } catch {
      // If backend chats endpoint fails, load from local storage or empty
      setChats([]);
    } finally {
      setChatsLoading(false);
    }
  };

  useEffect(() => {
    refreshChats();
  }, [location.pathname]);

  useEffect(() => {
    const applyTheme = () => {
      const pref = localStorage.getItem('clyptus-appearance');
      const media = window.matchMedia('(prefers-color-scheme: dark)');
      const isDark = pref === 'dark' || (!pref && true) || (pref === 'system' && media.matches);
      document.documentElement.classList.toggle('dark', isDark);
    };
    applyTheme();
    window.addEventListener('storage', applyTheme);
    window.addEventListener('theme-change', applyTheme);
    return () => {
      window.removeEventListener('storage', applyTheme);
      window.removeEventListener('theme-change', applyTheme);
    };
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname, location.search]);

  const normalizedQuery = query.trim().toLowerCase();

  const enrichedChats = useMemo(() => {
    return chats.map(c => ({
      ...c,
      isPinned: pinnedChatIds.includes(c.id),
    }));
  }, [chats, pinnedChatIds]);

  const filteredChats = useMemo(() => {
    return enrichedChats.filter(chat => !normalizedQuery || chat.title.toLowerCase().includes(normalizedQuery));
  }, [enrichedChats, normalizedQuery]);

  const filteredProjects = useMemo(() => {
    return projects.filter(project => !normalizedQuery || project.name.toLowerCase().includes(normalizedQuery));
  }, [projects, normalizedQuery]);

  const groupedChats = useMemo(() => {
    return ['Today', 'Yesterday', 'Earlier']
      .map(group => ({
        group,
        chats: filteredChats.filter(chat => dateGroup(chat) === group),
      }))
      .filter(group => group.chats.length > 0);
  }, [filteredChats]);

  const pinnedChats = useMemo(() => {
    return enrichedChats.filter(chat => chat.isPinned && (!normalizedQuery || chat.title.toLowerCase().includes(normalizedQuery)));
  }, [enrichedChats, normalizedQuery]);

  const pinnedProjects = useMemo(() => {
    return projects.filter(project => project.isPinned && (!normalizedQuery || project.name.toLowerCase().includes(normalizedQuery)));
  }, [projects, normalizedQuery]);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const handleNewChat = async () => {
    try {
      const newChat = await apiCreateChat('New SAP Chat');
      setChats(prev => [newChat, ...prev]);
      navigate(`/app/chat/${newChat.id}`);
    } catch {
      navigate('/app');
    }
  };

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm('Delete this chat?')) return;
    try {
      await apiDeleteChat(chatId);
      setChats(prev => prev.filter(c => c.id !== chatId));
      setPinnedChatIds(prev => {
        const next = prev.filter(id => id !== chatId);
        localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(next));
        return next;
      });
      if (location.pathname.includes(chatId)) {
        navigate('/app');
      }
    } catch (err) {
      console.error('Failed to delete chat:', err);
      setActionError('Could not delete chat.');
    }
  };

  const handleCreateProject = async (values: { name: string; description?: string }) => {
    try {
      setActionError(null);
      const project = projectService.createProject(values.name, values.description);
      setProjects(projectService.getProjects());
      setProjectModalOpen(false);
      navigate(`/app/projects/${project.id}`);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Could not create project.');
    }
  };

  const toggleChatPin = (chatId: string) => {
    setPinnedChatIds(prev => {
      const updated = prev.includes(chatId) ? prev.filter(id => id !== chatId) : [...prev, chatId];
      localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(updated));
      return updated;
    });
  };

  const toggleProjectPin = (projectId: string, currentPin: boolean) => {
    try {
      projectService.updateProject(projectId, { isPinned: !currentPin });
      setProjects(projectService.getProjects());
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Could not update pin.');
    }
  };

  const toggleSidebar = () => {
    if (window.innerWidth <= 900) {
      setSidebarOpen(prev => !prev);
    } else {
      setDesktopCollapsed(prev => !prev);
    }
  };

  const userInitial = user?.name ? user.name.charAt(0).toUpperCase() : 'C';

  return (
    <div className={`app-shell ${desktopCollapsed ? 'desktop-collapsed' : ''}`}>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarOpen ? 'app-sidebar-open' : ''}`} aria-label="Workspace sidebar">
        <div className="app-brand-row">
          <BrandLogo />
          <button
            className="icon-button mobile-sidebar-close ml-auto"
            type="button"
            aria-label="Close sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <button className="new-chat-button" type="button" onClick={handleNewChat}>
          <MessageSquarePlus size={17} />
          New chat
          <span>⌘ K</span>
        </button>

        <label className="conversation-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats and projects"
            aria-label="Search chats and projects"
          />
          <kbd>/</kbd>
        </label>

        {actionError && <p className="sidebar-error" role="alert">{actionError}</p>}

        {/* History area */}
        <div className="history-area">
          <div className="history-caption">
            CHATS{chatsLoading && <span>LOADING</span>}
          </div>

          {groupedChats.map(({ group, chats: items }) => (
            <div className="sidebar-group" key={group}>
              <span className="conversation-group">{group}</span>
              {items.map((chat) => {
                const isSelected = location.pathname === `/app/chat/${chat.id}`;
                return (
                  <div className={`sidebar-item-row ${isSelected ? 'selected-chat' : ''}`} key={chat.id}>
                    <NavLink
                      className={({ isActive }) => `conversation-link ${isActive ? 'active' : ''}`}
                      to={`/app/chat/${chat.id}`}
                      title={chat.title}
                    >
                      {chat.title}
                    </NavLink>
                    {isSelected && (
                      <button
                        className="sidebar-delete-btn text-slate-400 hover:text-rose-400 p-1 rounded hover:bg-rose-500/15 transition cursor-pointer shrink-0"
                        type="button"
                        aria-label={`Delete chat ${chat.title}`}
                        title="Delete chat"
                        onClick={(e) => handleDeleteChat(chat.id, e)}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                    <button
                      className={`sidebar-pin ${chat.isPinned ? 'is-pinned' : ''}`}
                      type="button"
                      aria-label={`${chat.isPinned ? 'Unpin' : 'Pin'} chat ${chat.title}`}
                      title={chat.isPinned ? 'Unpin chat' : 'Pin chat'}
                      onClick={() => toggleChatPin(chat.id)}
                    >
                      {chat.isPinned ? <PinOff size={13} /> : <Pin size={13} />}
                    </button>
                  </div>
                );
              })}
            </div>
          ))}

          {!chatsLoading && groupedChats.length === 0 && (
            <p className="sidebar-empty">
              {normalizedQuery ? 'No matching chats.' : 'Your conversations will appear here.'}
            </p>
          )}

          {/* Projects */}
          <div className="sidebar-section-heading">
            <span>PROJECTS</span>
            <button
              type="button"
              aria-label="Create a project"
              title="Create a project"
              onClick={() => setProjectModalOpen(true)}
            >
              <FolderPlus size={14} />
            </button>
          </div>

          {filteredProjects.map((project) => (
            <div className="sidebar-item-row" key={project.id}>
              <NavLink
                className={({ isActive }) => `conversation-link project-link ${isActive ? 'active' : ''}`}
                to={`/app/projects/${project.id}`}
                title={project.name}
              >
                {project.name}
              </NavLink>
              <button
                className={`sidebar-pin ${project.isPinned ? 'is-pinned' : ''}`}
                type="button"
                aria-label={`${project.isPinned ? 'Unpin' : 'Pin'} project ${project.name}`}
                title={project.isPinned ? 'Unpin project' : 'Pin project'}
                onClick={() => toggleProjectPin(project.id, project.isPinned)}
              >
                {project.isPinned ? <PinOff size={13} /> : <Pin size={13} />}
              </button>
            </div>
          ))}

          {filteredProjects.length === 0 && (
            <p className="sidebar-empty">
              {normalizedQuery ? 'No matching projects.' : 'No projects yet.'}
            </p>
          )}

          <button
            className="sidebar-new-project"
            type="button"
            onClick={() => setProjectModalOpen(true)}
          >
            <FolderPlus size={14} />
            New project
          </button>

          {/* Pinned section */}
          <div className="sidebar-section-heading pinned-heading">
            <span>PINNED</span>
          </div>

          {pinnedChats.length === 0 && pinnedProjects.length === 0 && (
            <p className="sidebar-empty">Pinned items appear here.</p>
          )}

          {pinnedChats.map((chat) => {
            const isSelected = location.pathname === `/app/chat/${chat.id}`;
            return (
              <div className={`sidebar-item-row ${isSelected ? 'selected-chat' : ''}`} key={`pinned-chat-${chat.id}`}>
                <NavLink className="pinned-link flex-1" to={`/app/chat/${chat.id}`}>
                  <Pin size={12} />
                  <span>{chat.title}</span>
                  <small>Chat</small>
                </NavLink>
                {isSelected && (
                  <button
                    className="sidebar-delete-btn text-slate-400 hover:text-rose-400 p-1 rounded hover:bg-rose-500/15 transition cursor-pointer shrink-0"
                    type="button"
                    aria-label={`Delete chat ${chat.title}`}
                    title="Delete chat"
                    onClick={(e) => handleDeleteChat(chat.id, e)}
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            );
          })}

          {pinnedProjects.map((project) => (
            <NavLink className="pinned-link" key={`pinned-proj-${project.id}`} to={`/app/projects/${project.id}`}>
              <Pin size={12} />
              <span>{project.name}</span>
              <small>Project</small>
            </NavLink>
          ))}
        </div>

        {/* Sidebar Nav */}
        <div className="sidebar-nav">
          <NavLink to="/app/settings">
            <Settings2 size={17} />
            Settings
          </NavLink>
        </div>

        {/* Bottom user card */}
        <div className="sidebar-bottom">
          <button
            className="workspace-help"
            type="button"
            onClick={() => setHelpModalOpen(true)}
            title="SAP + BRIM Assistant Guide"
          >
            <CircleHelp size={16} />
            <span>SAP + BRIM assistant</span>
            <span className="help-arrow">↗</span>
          </button>

          <button
            className="account-button"
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-expanded={menuOpen}
          >
            <span className="account-avatar">
              {user?.avatar ? <img src={user.avatar} alt="" /> : userInitial}
            </span>
            <span className="account-details">
              <strong>{user?.name || 'SAP Consultant'}</strong>
              <small>{user?.email || 'Enterprise User'}</small>
            </span>
            <ChevronDown size={15} />
          </button>

          {menuOpen && (
            <div className="account-menu">
              <NavLink to="/app/profile" onClick={() => setMenuOpen(false)}>
                <UserRound size={15} />
                Your profile
              </NavLink>
              <button type="button" onClick={handleLogout}>
                <LogOut size={15} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main Container */}
      <main className={`app-main ${isConversation ? 'app-main-chat' : ''}`}>
        {isConversation ? (
          <header className="app-topbar-minimal">
            <button
              className="chat-menu-toggle-btn"
              type="button"
              aria-label="Toggle chat menu"
              title={desktopCollapsed || !sidebarOpen ? 'Open chat menu' : 'Close chat menu'}
              onClick={toggleSidebar}
            >
              <Menu size={18} />
            </button>
            <div className="flex items-center gap-2 ml-3">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">SAP BRIM Assistant</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400 border border-orange-500/25 dark:border-orange-500/30 font-medium hidden sm:inline">
                Enterprise AI
              </span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white bg-slate-100 dark:bg-[#0c0c14] hover:bg-slate-200 dark:hover:bg-[#141420] border border-slate-200 dark:border-[#1e1e2c] transition cursor-pointer shadow-sm"
                type="button"
                onClick={handleNewChat}
                title="Start new chat"
              >
                <MessageSquarePlus size={14} className="text-orange-500 dark:text-orange-400" />
                <span className="hidden sm:inline">New chat</span>
              </button>
            </div>
          </header>
        ) : (
          <header className="app-topbar">
            <div className="app-topbar-left">
              <button
                className={`icon-button ${desktopCollapsed ? 'inline-flex' : 'app-mobile-menu'}`}
                type="button"
                aria-label="Toggle sidebar"
                title={desktopCollapsed ? 'Open sidebar' : 'Toggle sidebar'}
                onClick={toggleSidebar}
              >
                <Menu size={19} />
              </button>
              <div className="app-breadcrumb">
                <strong>
                  {location.pathname.split('/').pop()?.replace(/^\w/, (c) => c.toUpperCase()) || 'Workspace'}
                </strong>
              </div>
            </div>
            <div className="app-top-actions">
              <button className="top-new-chat" type="button" onClick={handleNewChat}>
                <MessageSquarePlus size={14} />
                New chat
              </button>
              <span className="backend-status">
                <i />
                Live connected
              </span>
              <span className="top-avatar">
                {user?.avatar ? <img src={user.avatar} alt="" /> : userInitial}
              </span>
            </div>
          </header>
        )}

        {/* Content Route */}
        <Outlet />
      </main>

      {projectModalOpen && (
        <ProjectModal
          error={actionError}
          onClose={() => {
            setProjectModalOpen(false);
            setActionError(null);
          }}
          onSave={handleCreateProject}
        />
      )}

      <AssistantGuideModal
        isOpen={helpModalOpen}
        onClose={() => setHelpModalOpen(false)}
      />
    </div>
  );
};
