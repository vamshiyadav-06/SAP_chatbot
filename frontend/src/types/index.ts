export interface User {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  created_at: string;
}

export interface Citation {
  id?: string;
  document: string;
  page: number;
  section?: string;
  score: number;
  snippet: string;
}

export interface WebSource {
  id?: string;
  title: string;
  url: string;
  domain: string;
  snippet: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  source_type?: 'knowledge_base' | 'web' | 'refusal' | 'error' | 'interrupted';
  grounding_score?: number;
  created_at: string;
  citations: Citation[];
  web_sources: WebSource[];
}

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}
