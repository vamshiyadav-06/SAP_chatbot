import React, { useState } from 'react';
import { ArrowUpRight, MessageSquarePlus, Pin, PinOff, Settings2, Trash2 } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ProjectModal } from '../components/projects/ProjectModal';
import { projectService } from '../services/projectService';
import type { Project } from '../types';

export const ProjectPage: React.FC = () => {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [projects, setProjects] = useState<Project[]>(() => projectService.getProjects());
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const project = projects.find((item) => item.id === projectId);

  if (!project) {
    return (
      <section className="workspace-page">
        <div className="workspace-heading">
          <div>
            <span className="eyebrow">PROJECT NOT FOUND</span>
            <h1>This project isn't available.</h1>
            <p>It may have been removed or updated.</p>
          </div>
        </div>
        <Link className="text-link" to="/app">
          Back to chats <ArrowUpRight size={15} />
        </Link>
      </section>
    );
  }

  const renameProject = (values: { name: string; description?: string }) => {
    setError(null);
    try {
      projectService.updateProject(projectId, values);
      setProjects(projectService.getProjects());
      setEditing(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update project.');
    }
  };

  const removeProject = () => {
    if (!window.confirm(`Delete "${project.name}"?`)) return;
    try {
      projectService.deleteProject(projectId);
      navigate('/app', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete project.');
    }
  };

  const togglePin = () => {
    try {
      projectService.updateProject(projectId, { isPinned: !project.isPinned });
      setProjects(projectService.getProjects());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update project pin.');
    }
  };

  return (
    <>
      <section className="workspace-page project-page">
        <div className="workspace-heading project-heading">
          <div>
            <span className="eyebrow">PROJECT</span>
            <h1>{project.name}</h1>
            <p>{project.description || 'A workspace folder for related SAP conversations.'}</p>
          </div>
          <div className="project-heading-actions">
            <button
              className="button button-outline button-small"
              type="button"
              onClick={togglePin}
            >
              {project.isPinned ? <PinOff size={14} /> : <Pin size={14} />}
              {project.isPinned ? 'Unpin' : 'Pin'}
            </button>
            <button
              className="button button-outline button-small"
              type="button"
              onClick={() => setEditing(true)}
            >
              <Settings2 size={14} />
              Rename
            </button>
            <button
              className="button button-dark button-small"
              type="button"
              onClick={() => navigate('/app')}
            >
              <MessageSquarePlus size={14} />
              New chat
            </button>
          </div>
        </div>

        {error && <p className="form-error" role="alert">{error}</p>}

        <div className="project-chat-heading">
          <div>
            <h2>Project Scope</h2>
            <span>Connected to Clyptusap.ai RAG Knowledge</span>
          </div>
        </div>

        <div className="project-chat-list">
          <div className="project-empty">
            <MessageSquarePlus size={24} className="text-orange-500 mb-2" />
            <strong>Start a new conversation in this project</strong>
            <span>All chats created while this project is active remain grouped in your workspace.</span>
            <button
              className="button button-dark button-small mt-3 cursor-pointer"
              type="button"
              onClick={() => navigate('/app')}
            >
              Start Chat <ArrowUpRight size={14} />
            </button>
          </div>
        </div>

        <button
          className="project-delete-button cursor-pointer"
          type="button"
          onClick={removeProject}
        >
          <Trash2 size={14} /> Delete project
        </button>
      </section>

      {editing && (
        <ProjectModal
          project={project}
          error={error}
          onClose={() => {
            setEditing(false);
            setError(null);
          }}
          onSave={renameProject}
        />
      )}
    </>
  );
};
