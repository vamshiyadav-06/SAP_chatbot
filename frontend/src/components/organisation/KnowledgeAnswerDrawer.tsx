import React, { useEffect, useId, useRef, useState } from 'react';
import { Heart, Loader2, Send, Trash2, X } from 'lucide-react';
import type { KnowledgeCategory, SharedAnswerDetail, SharedAnswerSummary } from '../../types';
import {
  apiOrgAddComment,
  apiOrgDeleteAnswer,
  apiOrgDeleteComment,
  apiOrgGetAnswer,
  apiOrgSetLike,
  apiOrgUpdateAnswerCategory,
} from '../../services/api';
import { AnswerMarkdown } from '../chat/AnswerMarkdown';
import { ConfirmDialog } from './OrgDialog';
import { COMMENT_MAX, formatDate, formatDateTime, initials, likersSummary, pluralise } from './orgFormat';
import { useDialog } from './useDialog';

type Pending = { kind: 'delete-answer' } | { kind: 'delete-comment'; commentId: string };

const message = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

/** Full shared answer with likes, comments and (for the sharer or an admin) topic change and removal. */
export function KnowledgeAnswerDrawer({
  answerId,
  section,
  categories,
  onClose,
  onSummaryChange,
  onDeleted,
}: {
  answerId: string;
  /** `comments`: opened from the comment button, so go straight to the discussion. */
  section?: 'comments';
  categories: KnowledgeCategory[];
  onClose: () => void;
  onSummaryChange: (id: string, patch: Partial<SharedAnswerSummary>, categoryChanged?: boolean) => void;
  onDeleted: (id: string) => void;
}) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  useDialog(panelRef, onClose);

  const [detail, setDetail] = useState<SharedAnswerDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [likeBusy, setLikeBusy] = useState(false);
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [comment, setComment] = useState('');
  const [commentBusy, setCommentBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [pendingBusy, setPendingBusy] = useState(false);
  const discussionRef = useRef<HTMLElement>(null);
  const commentInputRef = useRef<HTMLTextAreaElement>(null);

  // From the comment button: once the answer has loaded, show the discussion and focus the comment box.
  const loaded = detail !== null;
  useEffect(() => {
    if (section !== 'comments' || !loaded) return;
    discussionRef.current?.scrollIntoView({ block: 'start' });
    commentInputRef.current?.focus({ preventScroll: true });
  }, [section, loaded]);

  useEffect(() => {
    let cancelled = false;
    apiOrgGetAnswer(answerId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(message(err, 'Could not load this answer.'));
      });
    return () => {
      cancelled = true;
    };
  }, [answerId]);

  const toggleLike = async () => {
    if (!detail || likeBusy) return;
    setLikeBusy(true);
    setActionError(null);
    try {
      const result = await apiOrgSetLike(detail.id, !detail.liked_by_me);
      onSummaryChange(detail.id, { liked_by_me: result.liked, like_count: result.like_count });
      // Reload so the likers list shows the change.
      const fresh = await apiOrgGetAnswer(detail.id).catch(() => null);
      setDetail(fresh ?? { ...detail, liked_by_me: result.liked, like_count: result.like_count });
    } catch (err) {
      setActionError(message(err, 'Could not update your like.'));
    } finally {
      setLikeBusy(false);
    }
  };

  const changeCategory = async (category: string) => {
    if (!detail || category === detail.category) return;
    setCategoryBusy(true);
    setActionError(null);
    try {
      const updated = await apiOrgUpdateAnswerCategory(detail.id, category);
      const label = updated?.category_label ?? categories.find((c) => c.key === category)?.label ?? category;
      setDetail(updated ?? { ...detail, category, category_label: label });
      onSummaryChange(detail.id, { category, category_label: label }, true);
    } catch (err) {
      setActionError(message(err, 'Could not change the topic.'));
    } finally {
      setCategoryBusy(false);
    }
  };

  const addComment = async (event: React.FormEvent) => {
    event.preventDefault();
    const body = comment.trim();
    if (!detail || !body || commentBusy) return;
    setCommentBusy(true);
    setActionError(null);
    try {
      const created = await apiOrgAddComment(detail.id, body);
      const comments = [...detail.comments, created];
      setDetail({ ...detail, comments, comment_count: comments.length });
      onSummaryChange(detail.id, { comment_count: comments.length });
      setComment('');
    } catch (err) {
      setActionError(message(err, 'Could not post your comment.'));
    } finally {
      setCommentBusy(false);
    }
  };

  const confirmPending = async () => {
    if (!detail || !pending) return;
    setPendingBusy(true);
    setActionError(null);
    try {
      if (pending.kind === 'delete-answer') {
        await apiOrgDeleteAnswer(detail.id);
        setPending(null);
        onDeleted(detail.id);
        return;
      }
      await apiOrgDeleteComment(detail.id, pending.commentId);
      const comments = detail.comments.filter((c) => c.id !== pending.commentId);
      setDetail({ ...detail, comments, comment_count: comments.length });
      onSummaryChange(detail.id, { comment_count: comments.length });
      setPending(null);
    } catch (err) {
      setActionError(message(err, 'That did not work. Please try again.'));
      setPending(null);
    } finally {
      setPendingBusy(false);
    }
  };

  return (
    <div
      className="org-drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div ref={panelRef} className="org-drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="org-drawer-head">
          <span className="org-app-eyebrow">Shared answer</span>
          <button type="button" className="org-icon-btn" onClick={onClose} aria-label="Close answer">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="org-drawer-body">
          {!detail && !loadError && (
            <div className="org-drawer-meta" role="status">
              <span className="org-spinner" aria-hidden="true" /> Loading answer…
            </div>
          )}
          {loadError && (
            <p className="org-alert" role="alert">
              {loadError}
            </p>
          )}
          {!detail && <h2 id={titleId} className="visually-hidden">Shared answer</h2>}

          {detail && (
            <>
              <div className="org-card-top">
                <span className="org-pill">{detail.category_label}</span>
                <span className="org-card-date">
                  Shared by {detail.shared_by_name} · {formatDate(detail.created_at)}
                </span>
              </div>
              <h2 id={titleId}>{detail.question}</h2>

              {actionError && (
                <p className="org-alert" role="alert">
                  {actionError}
                </p>
              )}

              <div className="org-answer prose-sap text-slate-800 dark:text-slate-200 leading-relaxed break-words">
                <AnswerMarkdown content={detail.answer} />
              </div>

              <div className="org-drawer-meta">
                <button
                  type="button"
                  className="org-like-btn"
                  aria-pressed={detail.liked_by_me}
                  onClick={toggleLike}
                  disabled={likeBusy}
                >
                  <Heart size={14} aria-hidden="true" />
                  {detail.liked_by_me ? 'Liked' : 'Like'} · {detail.like_count}
                </button>
                <span>{likersSummary(detail.likers.map((l) => l.name))}</span>
              </div>

              {detail.likers.length > 0 && (
                <section aria-label="Members who liked this answer">
                  <h3 className="org-section-title">Liked by</h3>
                  <ul className="org-likers">
                    {detail.likers.map((liker) => (
                      <li key={`${liker.name}-${liker.liked_at}`} title={`Liked ${formatDateTime(liker.liked_at)}`}>
                        <span className="org-avatar" aria-hidden="true">
                          {initials(liker.name)}
                        </span>
                        {liker.name}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section aria-label="Discussion" ref={discussionRef}>
                <h3 className="org-section-title">Discussion · {pluralise(detail.comments.length, 'comment')}</h3>
                {detail.comments.length > 0 ? (
                  <ul className="org-comments">
                    {detail.comments.map((c) => (
                      <li className="org-comment" key={c.id}>
                        <span className="org-avatar" aria-hidden="true">
                          {initials(c.author_name)}
                        </span>
                        <div className="org-comment-body">
                          <div className="org-comment-head">
                            <strong>{c.author_name}</strong>
                            <span>{formatDateTime(c.created_at)}</span>
                          </div>
                          <p>{c.body}</p>
                        </div>
                        {c.can_delete && (
                          <button
                            type="button"
                            className="org-icon-btn"
                            aria-label={`Delete comment by ${c.author_name}`}
                            onClick={() => setPending({ kind: 'delete-comment', commentId: c.id })}
                          >
                            <Trash2 size={15} aria-hidden="true" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="org-form-note">No comments yet. Start the discussion.</p>
                )}
                <form className="org-comment-form" onSubmit={addComment} style={{ marginTop: 12 }}>
                  <label htmlFor="org-comment-input" className="visually-hidden">
                    Add a comment
                  </label>
                  <textarea
                    ref={commentInputRef}
                    id="org-comment-input"
                    className="org-textarea"
                    rows={3}
                    maxLength={COMMENT_MAX}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Add a comment for your team…"
                  />
                  <div className="org-comment-form-foot">
                    <span className="org-char-count">
                      {comment.length}/{COMMENT_MAX}
                    </span>
                    <button type="submit" className="org-btn org-btn-primary org-btn-sm" disabled={!comment.trim() || commentBusy}>
                      {commentBusy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Send size={14} aria-hidden="true" />}
                      Comment
                    </button>
                  </div>
                </form>
              </section>

              {detail.can_edit && (
                <section className="org-manage" aria-label="Manage this answer">
                  <div className="org-field">
                    <label htmlFor="org-answer-category">Topic</label>
                    <select
                      id="org-answer-category"
                      className="org-select"
                      value={detail.category}
                      disabled={categoryBusy}
                      onChange={(e) => changeCategory(e.target.value)}
                    >
                      {categories.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label}
                        </option>
                      ))}
                      {!categories.some((c) => c.key === detail.category) && (
                        <option value={detail.category}>{detail.category_label}</option>
                      )}
                    </select>
                  </div>
                  <button type="button" className="org-btn org-btn-danger" onClick={() => setPending({ kind: 'delete-answer' })}>
                    <Trash2 size={14} aria-hidden="true" /> Remove from hub
                  </button>
                </section>
              )}
            </>
          )}
        </div>
      </div>

      {pending && (
        <ConfirmDialog
          title={pending.kind === 'delete-answer' ? 'Remove this answer?' : 'Delete this comment?'}
          message={
            pending.kind === 'delete-answer'
              ? 'The answer, its likes and its comments will be removed from the knowledge hub for everyone. The original chat is not affected.'
              : 'The comment will be removed for everyone in your organisation.'
          }
          confirmLabel={pending.kind === 'delete-answer' ? 'Remove answer' : 'Delete comment'}
          busy={pendingBusy}
          onConfirm={confirmPending}
          onCancel={() => setPending(null)}
        />
      )}
    </div>
  );
}
