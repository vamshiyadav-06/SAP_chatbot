import React, { useCallback, useEffect, useState } from 'react';
import { PageMeta } from '../../components/ui/PageMeta';
import { KnowledgeHubView } from '../../components/organisation/KnowledgeHubView';
import { KnowledgeAnswerDrawer } from '../../components/organisation/KnowledgeAnswerDrawer';
import { useAuth } from '../../context/AuthContext';
import { isOrgAdmin } from '../../layouts/accountRouting';
import { apiOrgGetCategories, apiOrgGetMe, apiOrgListKnowledge, apiOrgSetLike } from '../../services/api';
import type { KnowledgeCategory, OrgMe, SharedAnswerSummary } from '../../types';
import '../../components/organisation/organisation.css';

const PAGE_SIZE = 20;
const SEARCH_DELAY_MS = 300;

interface ListState {
  key: string;
  total: number;
  items: SharedAnswerSummary[];
  error: string | null;
}

const listKeyOf = (category: string, query: string) => `${category}\u0000${query}`;

/** /app/organisation: organisation header, topic navigation, search and the shared answers. */
export const OrgKnowledgeHubPage: React.FC = () => {
  const { user } = useAuth();
  const [me, setMe] = useState<OrgMe | null>(null);
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [list, setList] = useState<ListState | null>(null);
  const [reloadCount, setReloadCount] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [likeBusyIds, setLikeBusyIds] = useState<ReadonlySet<string>>(() => new Set());
  const [openId, setOpenId] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<'comments' | undefined>(undefined);
  const [actionError, setActionError] = useState<string | null>(null);

  const currentKey = listKeyOf(category, query);

  const refreshCategories = useCallback(() => {
    apiOrgGetCategories()
      .then(setCategories)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiOrgGetMe()
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch(() => undefined);
    refreshCategories();
    return () => {
      cancelled = true;
    };
  }, [refreshCategories]);

  // Debounce typing before searching.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    const key = listKeyOf(category, query);
    apiOrgListKnowledge({ category: category || undefined, q: query || undefined, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (!cancelled) setList({ key, total: res.total, items: res.items, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setList({ key, total: 0, items: [], error: err instanceof Error ? err.message : 'Could not load shared answers.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [category, query, reloadCount]);

  const current = list && list.key === currentKey ? list : null;

  const patchItem = useCallback((id: string, patch: Partial<SharedAnswerSummary>) => {
    setList((prev) =>
      prev ? { ...prev, items: prev.items.map((item) => (item.id === id ? { ...item, ...patch } : item)) } : prev,
    );
  }, []);

  const toggleLike = async (answer: SharedAnswerSummary) => {
    if (likeBusyIds.has(answer.id)) return;
    const liked = !answer.liked_by_me;
    setActionError(null);
    setLikeBusyIds((prev) => new Set([...prev, answer.id]));
    patchItem(answer.id, { liked_by_me: liked, like_count: Math.max(0, answer.like_count + (liked ? 1 : -1)) });
    try {
      const result = await apiOrgSetLike(answer.id, liked);
      patchItem(answer.id, { liked_by_me: result.liked, like_count: result.like_count });
    } catch (err) {
      patchItem(answer.id, { liked_by_me: answer.liked_by_me, like_count: answer.like_count });
      setActionError(err instanceof Error ? err.message : 'Could not update your like.');
    } finally {
      setLikeBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(answer.id);
        return next;
      });
    }
  };

  const loadMore = async () => {
    if (!current || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await apiOrgListKnowledge({
        category: category || undefined,
        q: query || undefined,
        limit: PAGE_SIZE,
        offset: current.items.length,
      });
      setList((prev) =>
        prev && prev.key === current.key
          ? {
              ...prev,
              total: res.total,
              items: [...prev.items, ...res.items.filter((item) => !prev.items.some((p) => p.id === item.id))],
            }
          : prev,
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not load more answers.');
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSummaryChange = (id: string, patch: Partial<SharedAnswerSummary>, categoryChanged?: boolean) => {
    patchItem(id, patch);
    if (categoryChanged) {
      refreshCategories();
      // Filtered by topic: the answer may no longer belong in this list.
      if (category) setReloadCount((n) => n + 1);
    }
  };

  const handleDeleted = (id: string) => {
    setOpenId(null);
    setList((prev) =>
      prev ? { ...prev, total: Math.max(0, prev.total - 1), items: prev.items.filter((item) => item.id !== id) } : prev,
    );
    refreshCategories();
  };

  const closeDrawer = useCallback(() => setOpenId(null), []);

  return (
    <>
      <PageMeta title="Knowledge Hub" description="Your organisation's shared SAP BRIM answers, organised by topic." />
      {actionError && (
        <div className="org-app" style={{ paddingBottom: 0 }}>
          <p className="org-alert" role="alert">
            {actionError}
          </p>
        </div>
      )}
      <KnowledgeHubView
        me={me}
        organisationName={user?.organization_name}
        canManage={Boolean(me?.can_manage) || isOrgAdmin(user)}
        categories={categories}
        activeCategory={category}
        onSelectCategory={setCategory}
        search={search}
        onSearchChange={setSearch}
        items={current && !current.error ? current.items : null}
        total={current?.total ?? 0}
        error={current?.error ?? null}
        onRetry={() => setReloadCount((n) => n + 1)}
        onOpen={(id, section) => {
          setOpenSection(section);
          setOpenId(id);
        }}
        onToggleLike={toggleLike}
        likeBusyIds={likeBusyIds}
        onLoadMore={loadMore}
        loadingMore={loadingMore}
      />
      {openId && (
        <KnowledgeAnswerDrawer
          key={openId}
          answerId={openId}
          section={openSection}
          categories={categories}
          onClose={closeDrawer}
          onSummaryChange={handleSummaryChange}
          onDeleted={handleDeleted}
        />
      )}
    </>
  );
};
