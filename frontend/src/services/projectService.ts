import type { Project } from '../types';

const STORAGE_KEY = 'clyptus_projects';

export const projectService = {
  getProjects(): Project[] {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      return data ? JSON.parse(data) : [
        {
          id: 'proj_brim_core',
          name: 'SAP BRIM Architecture',
          description: 'BRIM Billing, Invoicing and Charging integration flows.',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          isPinned: true,
        }
      ];
    } catch {
      return [];
    }
  },

  createProject(name: string, description?: string): Project {
    const projects = this.getProjects();
    const newProj: Project = {
      id: 'proj_' + Date.now().toString(36),
      name,
      description,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      isPinned: false,
    };
    const updated = [newProj, ...projects];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return newProj;
  },

  updateProject(id: string, updates: Partial<Pick<Project, 'name' | 'description' | 'isPinned'>>): Project {
    const projects = this.getProjects();
    let updatedProj: Project | null = null;
    const updated = projects.map(p => {
      if (p.id === id) {
        updatedProj = { ...p, ...updates, updatedAt: new Date().toISOString() };
        return updatedProj;
      }
      return p;
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    if (!updatedProj) throw new Error('Project not found');
    return updatedProj;
  },

  deleteProject(id: string): void {
    const projects = this.getProjects().filter(p => p.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
  }
};
