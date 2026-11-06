import { Heart, MessageCircle } from 'lucide-react';
import type { SharedAnswerSummary } from '../../types';
import { formatDate, initials, markdownToPlainText, pluralise } from './orgFormat';

/** One shared answer in the knowledge hub list. Clicking the answer (question or preview) opens it; the
 * comment button opens it at the discussion instead. */
export function KnowledgeAnswerCard({
  answer,
  likeBusy = false,
  onOpen,
  onToggleLike,
}: {
  answer: SharedAnswerSummary;
  likeBusy?: boolean;
  onOpen: (id: string, section?: 'comments') => void;
  onToggleLike: (answer: SharedAnswerSummary) => void;
}) {
  return (
    <article
      className="org-card"
      aria-labelledby={`org-answer-${answer.id}`}
      style={{ cursor: 'pointer' }}
      onClick={(event) => {
        // The buttons (like, comment, question) do their own thing; anywhere else on the card opens the answer.
        if ((event.target as HTMLElement).closest('button, a')) return;
        onOpen(answer.id);
      }}
    >
      <div className="org-card-top">
        <span className="org-pill">{answer.category_label}</span>
        <time className="org-card-date" dateTime={answer.created_at}>
          {formatDate(answer.created_at)}
        </time>
      </div>
      <h3 className="org-card-heading">
        <button
          type="button"
          id={`org-answer-${answer.id}`}
          className="org-card-question"
          onClick={() => onOpen(answer.id)}
        >
          {answer.question}
        </button>
      </h3>
      <p className="org-card-preview">{markdownToPlainText(answer.answer_preview)}</p>
      <div className="org-card-foot">
        <span className="org-card-by">
          <span className="org-avatar" aria-hidden="true">
            {initials(answer.shared_by_name)}
          </span>
          Shared by {answer.shared_by_name}
        </span>
        <button
          type="button"
          className="org-like-btn"
          aria-pressed={answer.liked_by_me}
          aria-label={`${answer.liked_by_me ? 'Unlike' : 'Like'} this answer, ${pluralise(answer.like_count, 'like')}`}
          disabled={likeBusy}
          onClick={() => onToggleLike(answer)}
        >
          <Heart size={14} aria-hidden="true" />
          <span>{answer.like_count}</span>
        </button>
        <button
          type="button"
          className="org-like-btn"
          aria-label={`Open comments, ${pluralise(answer.comment_count, 'comment')}`}
          onClick={() => onOpen(answer.id, 'comments')}
        >
          <MessageCircle size={14} aria-hidden="true" />
          <span>{answer.comment_count}</span>
        </button>
      </div>
    </article>
  );
}
