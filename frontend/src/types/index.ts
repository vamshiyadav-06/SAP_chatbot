export interface User {
  id: string;
  email: string;
  name: string;
  is_admin?: boolean;
  role?: string;
  isGuest?: boolean;
  avatar?: string;
  dateOfBirth?: string;
  profileCompleted?: boolean;
  created_at?: string;
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
  source_type?: 'knowledge_base' | 'web' | 'combined' | 'refusal' | 'error' | 'interrupted' | 'security_policy';
  grounding_score?: number;
  confidence?: number;
  grounding?: string;
  verification_status?: 'verified' | 'partial' | 'unverified' | 'abstention' | 'restricted';
  internal_evidence_confidence?: number;
  selected_evidence_quality?: number;
  kb_score?: number;
  web_score?: number;
  winning_score?: number;
  is_in_rag_pipeline?: boolean;
  external_search_used?: boolean;
  follow_up_questions?: string[];
  security_restricted?: boolean;
  violation_category?: string;
  created_at: string;
  citations: Citation[];
  web_sources: WebSource[];
}

export interface Chat {
  id: string;
  user_id?: string;
  projectId?: string;
  title: string;
  created_at: string;
  updated_at: string;
  isPinned?: boolean;
  message_count?: number;
}

export interface Project {
  id: string;
  userId?: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
  isPinned: boolean;
}
