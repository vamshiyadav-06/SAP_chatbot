export interface User {
  id: string;
  email: string;
  name: string;
  is_admin?: boolean;
  role?: string;
  avatar?: string;
  dateOfBirth?: string;
  profileCompleted?: boolean;
  created_at?: string;
}

export interface Citation {
  id?: string;
  chunk_id?: string;
  source_type?: string;
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

export interface WebImage {
  url: string;
  description?: string | null;
  alt_text?: string | null;
  source_url?: string | null;
  source_title?: string | null;
  relevance_score?: number | null;
}

export interface DocumentAttachment {
  name: string;
  file_type?: string;
  size_bytes?: number;
  page_count?: number;
  text?: string;
  preview?: string;
}

export type MessageFeedback = 'up' | 'down';

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments?: DocumentAttachment[];
  source_type?: 'knowledge_base' | 'github_repo' | 'web' | 'combined' | 'abstention' | 'insufficient' | 'refusal' | 'error' | 'interrupted' | 'security_policy' | 'conversational' | 'attached_document';
  grounding_score?: number;
  confidence?: number;
  grounding?: string;
  verification_status?: 'verified' | 'partial' | 'unverified' | 'abstention' | 'restricted';
  internal_evidence_confidence?: number;
  selected_evidence_quality?: number;
  kb_score?: number;
  web_score?: number;
  winning_score?: number;
  source_scores?: Record<string, number>;
  is_in_rag_pipeline?: boolean;
  external_search_used?: boolean;
  follow_up_questions?: string[];
  feedback?: MessageFeedback | null;
  security_restricted?: boolean;
  violation_category?: string;
  created_at: string;
  citations: Citation[];
  web_sources: WebSource[];
  images?: WebImage[];
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

export interface KBDocument {
  id: string;
  filename: string;
  title: string;
  file_type: string;
  file_size_bytes: number;
  file_size_formatted: string;
  page_count: number;
  chunk_count: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  stage: string;
  error_message?: string | null;
  vector_indexed: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface DocumentCounts {
  all: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  total_chunks: number;
}

export interface ProcessingProgress {
  is_processing: boolean;
  total_selected: number;
  completed_count: number;
  processing_count: number;
  pending_count: number;
  failed_count: number;
  total_chunks_generated: number;
  total_embeddings_stored: number;
  overall_progress_pct: number;
  current_document_id?: string | null;
  current_document_name?: string | null;
  current_stage: string;
  verification_status: 'Pending' | 'Successful' | 'Partial' | 'Failed';
  summary?: {
    documents_processed: number;
    completed_documents?: number;
    chunks_generated: number;
    embeddings_stored: number;
    failed_documents: number;
    vector_database_verification: string;
  } | null;
  recent_logs?: string[];
  timestamp?: string;
}

export interface DocumentListResponse {
  documents: KBDocument[];
  total: number;
  page: number;
  page_size: number;
  counts: DocumentCounts;
}

