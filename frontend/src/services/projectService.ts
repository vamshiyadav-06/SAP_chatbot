import type { Project } from '../types';
import { userStorageKey } from './userStorage';

const defaultProjects = (): Project[] => [{
  id: 'proj_brim_core',
  name: 'SAP BRIM Architecture',
  description: 'BRIM Billing, Invoicing and Charging integration flows.',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  isPinned: true,
}];

const storageKey = (userId: string) => userStorageKey(userId, 'projects');

export const projectService = {
  getProjects(userId: string): Project[] {
    try {
      const data = localStorage.getItem(storageKey(userId));
      return data ? JSON.parse(data) : defaultProjects();
    } catch {
      return [];
    }
  },

  createProject(userId: string, name: string, description?: string): Project {
    const projects = this.getProjects(userId);
    const newProj: Project = {
      id: 'proj_' + Date.now().toString(36),
      name,
      description,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      isPinned: false,
    };
    localStorage.setItem(storageKey(userId), JSON.stringify([newProj, ...projects]));
    return newProj;
  },

  updateProject(userId: string, id: string, updates: Partial<Pick<Project, 'name' | 'description' | 'isPinned'>>): Project {
    const projects = this.getProjects(userId);
    let updatedProj: Project | null = null;
    const updated = projects.map((project) => {
      if (project.id !== id) return project;
      updatedProj = { ...project, ...updates, updatedAt: new Date().toISOString() };
      return updatedProj;
    });
    localStorage.setItem(storageKey(userId), JSON.stringify(updated));
    if (!updatedProj) throw new Error('Project not found');
    return updatedProj;
  },

  deleteProject(userId: string, id: string): void {
    const projects = this.getProjects(userId).filter((project) => project.id !== id);
    localStorage.setItem(storageKey(userId), JSON.stringify(projects));
  },
};
