import { BookOpen, Building2, LayoutDashboard, MessageSquarePlus, Search, SearchX, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { KnowledgeCategory, OrgMe, SharedAnswerSummary } from '../../types';
import { ORG_ADMIN_PATH } from '../../layouts/accountRouting';
import { KnowledgeAnswerCard } from './KnowledgeAnswerCard';
import { ORG_ROLE_LABELS, initials, pluralise } from './orgFormat';

export interface KnowledgeHubViewProps {
  me: OrgMe | null;
  /** Fallback while /org/me loads (from the signed-in user). */
  organisationName?: string | null;
  canManage: boolean;
  categories: KnowledgeCategory[];
  activeCategory: string;
  onSelectCategory: (key: string) => void;
  search: string;
  onSearchChange: (value: string) => void;
  /** null while the first page loads. */
  items: SharedAnswerSummary[] | null;
  total: number;
  error: string | null;
  onRetry: () => void;
  onOpen: (id: string, section?: 'comments') => void;
  onToggleLike: (answer: SharedAnswerSummary) => void;
  likeBusyIds: ReadonlySet<string>;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

/** Member dashboard and Shared Knowledge Hub (presentational; data comes from OrgKnowledgeHubPage). */
export function KnowledgeHubView({
  me,
  organisationName,
  canManage,
  categories,
  activeCategory,
  onSelectCategory,
  search,
  onSearchChange,
  items,
  total,
  error,
  onRetry,
  onOpen,
  onToggleLike,
  likeBusyIds,
  onLoadMore,
  loadingMore = false,
}: KnowledgeHubViewProps) {
  const name = me?.organisation.name ?? organisationName ?? 'Your organisation';
  const allCount = categories.reduce((sum, c) => sum + (c.count ?? 0), 0);
  const filtered = Boolean(activeCategory || search.trim());
  const activeLabel = categories.find((c) => c.key === activeCategory)?.label;

  return (
    <div className="org-app">
      <header className="org-app-header">
        <div className="org-app-identity">
          <span className="org-app-logo" aria-hidden="true">
            {initials(name)}
          </span>
          <div>
            <span className="org-app-eyebrow">Organisation workspace</span>
            <h1>{name}</h1>
            <div className="org-app-meta">
              {me && <span className="org-badge org-badge-brand">{ORG_ROLE_LABELS[me.role] ?? me.role}</span>}
              {me && (
                <span className="inline-flex items-center gap-1">
                  <Building2 size={13} aria-hidden="true" />
                  {pluralise(me.organisation.member_count, 'member')}
                </span>
              )}
              <span>{pluralise(allCount, 'shared answer')}</span>
            </div>
          </div>
        </div>
        <div className="org-app-actions">
          <Link className="org-btn" to="/app">
            <MessageSquarePlus size={15} aria-hidden="true" /> Ask a question
          </Link>
          {canManage && (
            <Link className="org-btn org-btn-primary" to={ORG_ADMIN_PATH}>
              <LayoutDashboard size={15} aria-hidden="true" /> Admin dashboard
            </Link>
          )}
        </div>
      </header>

      <div className="org-hub">
        <nav className="org-topic-nav" aria-label="Knowledge topics">
          <span className="org-topic-nav-title">Topics</span>
          <button
            type="button"
            className="org-topic-btn"
            aria-current={activeCategory === '' ? 'true' : undefined}
            onClick={() => onSelectCategory('')}
          >
            <span>All topics</span>
            <span className="org-topic-count">{allCount}</span>
          </button>
          {categories.map((category) => (
            <button
              type="button"
              key={category.key}
              className="org-topic-btn"
              aria-current={activeCategory === category.key ? 'true' : undefined}
              onClick={() => onSelectCategory(category.key)}
            >
              <span>{category.label}</span>
              <span className="org-topic-count">{category.count}</span>
            </button>
          ))}
        </nav>

        <section className="org-hub-main" aria-labelledby="org-hub-heading">
          <h2 id="org-hub-heading" className="visually-hidden">
            Shared Knowledge Hub
          </h2>
          <div className="org-toolbar">
            <div className="org-search">
              <Search size={16} aria-hidden="true" />
              <label htmlFor="org-hub-search" className="visually-hidden">
                Search shared answers
              </label>
              <input
                id="org-hub-search"
                type="search"
                autoComplete="off"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search questions and answers"
              />
              {search && (
                <button type="button" className="org-icon-btn" aria-label="Clear search" onClick={() => onSearchChange('')}>
                  <X size={15} aria-hidden="true" />
                </button>
              )}
            </div>
            {items && (
              <span className="org-result-count" role="status">
                {pluralise(total, 'answer')}
                {activeLabel ? ` in ${activeLabel}` : ''}
              </span>
            )}
          </div>

          {error && (
            <div className="org-alert" role="alert" style={{ marginTop: 16 }}>
              <span>{error}</span>
              <button type="button" className="org-link-btn" onClick={onRetry}>
                Try again
              </button>
            </div>
          )}

          {!items && !error && (
            <div className="org-card-list" aria-busy="true" aria-label="Loading shared answers">
              <div className="org-skeleton" />
              <div className="org-skeleton" />
              <div className="org-skeleton" />
            </div>
          )}

          {items && items.length === 0 && !filtered && (
            <div className="org-empty">
              <span className="org-empty-icon" aria-hidden="true">
                <BookOpen size={24} />
              </span>
              <h3>No shared answers yet</h3>
              <p>Useful answers from your team's chats appear here once someone shares them. Here is how:</p>
              <ol className="org-empty-steps">
                <li>
                  <span>1</span> Ask an SAP BRIM question in the chat.
                </li>
                <li>
                  <span>2</span> Under a helpful answer, click <strong>Org</strong>.
                </li>
                <li>
                  <span>3</span> Or open <strong>Share</strong> and choose <strong>Share to Knowledge Hub</strong>.
                </li>
              </ol>
              <Link className="org-btn org-btn-primary" to="/app">
                <MessageSquarePlus size={15} aria-hidden="true" /> Start a chat
              </Link>
            </div>
          )}

          {items && items.length === 0 && filtered && (
            <div className="org-empty">
              <span className="org-empty-icon" aria-hidden="true">
                <SearchX size={24} />
              </span>
              <h3>No matching answers</h3>
              <p>Try another topic or search term, or share an answer on this topic from the chat.</p>
              <button
                type="button"
                className="org-btn"
                onClick={() => {
                  onSearchChange('');
                  onSelectCategory('');
                }}
              >
                Show all answers
              </button>
            </div>
          )}

          {items && items.length > 0 && (
            <div className="org-card-list">
              {items.map((answer) => (
                <KnowledgeAnswerCard
                  key={answer.id}
                  answer={answer}
                  likeBusy={likeBusyIds.has(answer.id)}
                  onOpen={onOpen}
                  onToggleLike={onToggleLike}
                />
              ))}
            </div>
          )}

          {items && onLoadMore && items.length < total && (
            <div className="org-load-more">
              <button type="button" className="org-btn" onClick={onLoadMore} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : `Show more (${total - items.length} remaining)`}
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
