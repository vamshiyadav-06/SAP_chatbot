import { useEffect, useState, type FormEvent } from 'react';
import { X } from 'lucide-react';
import type { Project } from '../../types';

interface ProjectModalProps {
  project?: Project | null;
  isSaving?: boolean;
  error?: string | null;
  onClose(): void;
  onSave(values: { name: string; description?: string }): Promise<void> | void;
}

export function ProjectModal({ project, isSaving = false, error, onClose, onSave }: ProjectModalProps) {
  const [name, setName] = useState(project?.name ?? '');
  const [description, setDescription] = useState(project?.description ?? '');
  const [validationError, setValidationError] = useState('');

  useEffect(() => {
    setName(project?.name ?? '');
    setDescription(project?.description ?? '');
  }, [project]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setValidationError('Project name is required.');
      return;
    }
    setValidationError('');
    await onSave({ name: name.trim(), ...(description.trim() ? { description: description.trim() } : {}) });
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="project-modal" role="dialog" aria-modal="true" aria-labelledby="project-modal-title">
        <div className="project-modal-heading">
          <div>
            <span className="eyebrow">PROJECT WORKSPACE</span>
            <h2 id="project-modal-title">{project ? 'Rename project' : 'Create a project'}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close dialog" onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="project-name">Project name</label>
          <input
            id="project-name"
            autoFocus
            value={name}
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. SAP BRIM Billing Flow"
            required
          />
          <label htmlFor="project-description">
            Description <span>Optional</span>
          </label>
          <textarea
            id="project-description"
            value={description}
            maxLength={500}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What SAP topics or workflows belong in this project?"
            rows={3}
          />
          {(validationError || error) && <p className="form-error" role="alert">{validationError || error}</p>}
          <div className="project-modal-actions">
            <button className="button button-outline button-small" type="button" onClick={onClose} disabled={isSaving}>
              Cancel
            </button>
            <button className="button button-dark button-small" type="submit" disabled={isSaving}>
              {isSaving ? 'Saving…' : project ? 'Save changes' : 'Create project'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
