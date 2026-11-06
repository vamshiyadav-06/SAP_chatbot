import React, { useEffect, useState } from 'react';
import { Brain, Trash2 } from 'lucide-react';
import { apiDeleteAllMemories, apiDeleteMemory, apiListMemories, type SavedMemory } from '../../services/api';

/** Settings: what the user asked the assistant to remember ("save it"). Used in all of their chats. */
export const SavedMemoryCard: React.FC = () => {
  const [items, setItems] = useState<SavedMemory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiListMemories()
      .then((list) => !cancelled && setItems(list))
      .catch(() => !cancelled && setError('Your saved memory is not available right now.'));
    return () => {
      cancelled = true;
    };
  }, []);

  const remove = async (id: string) => {
    try {
      await apiDeleteMemory(id);
      setItems((prev) => (prev ?? []).filter((m) => m.id !== id));
    } catch {
      setError('Could not delete this item.');
    }
  };

  const clearAll = async () => {
    if (!window.confirm('Delete everything the assistant has saved about you?')) return;
    try {
      await apiDeleteAllMemories();
      setItems([]);
    } catch {
      setError('Could not delete your saved memory.');
    }
  };

  return (
    <div className="settings-group">
      <div className="settings-group-heading">
        <h2>Saved memory</h2>
        <p>
          Say “save it” or “remember that …” in any chat. Saved items are used to answer you in all of your chats,
          and only you can see them.
        </p>
      </div>
      {error && <p role="alert">{error}</p>}
      {items && items.length === 0 && !error && (
        <div className="settings-row">
          <div className="settings-row-icon">
            <span className="account-avatar" aria-hidden="true"><Brain size={14} /></span>
          </div>
          <div>
            <strong>Nothing saved yet</strong>
            <span>Try: “Remember that I work on SAP BRIM billing.”</span>
          </div>
        </div>
      )}
      {(items ?? []).map((item) => (
        <div className="settings-row" key={item.id}>
          <div className="settings-row-icon">
            <span className="account-avatar" aria-hidden="true"><Brain size={14} /></span>
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{item.content}</span>
          </div>
          <button type="button" className="item-action-btn" aria-label="Delete saved item" title="Delete" onClick={() => remove(item.id)}>
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      {items && items.length > 1 && (
        <button type="button" className="settings-row" onClick={clearAll}>
          <strong>Delete all saved memory</strong>
        </button>
      )}
    </div>
  );
};
