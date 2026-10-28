import type { User, Chat, Message, MessageFeedback,Citation, WebSource, WebImage, DocumentAttachment, DocumentListResponse, ProcessingProgress } from '../types';

const API_BASE_URL = 'http://localhost:8000/api';

export const getStoredToken = (): string | null => {
  return localStorage.getItem('sap_assistant_token');
};

export const setStoredToken = (token: string): void => {
  localStorage.setItem('sap_assistant_token', token);
};

export const clearStoredToken = (): void => {
  localStorage.removeItem('sap_assistant_token');
};

export const apiLogout = async (): Promise<void> => {
  await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', headers: authHeaders() });
};

const authHeaders = (): Record<string, string> => {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const SERVER_UNREACHABLE = 'Cannot reach the server. Make sure the backend is running on http://localhost:8000.';
const SERVER_TIMEOUT = 'The server stopped responding. Please try again.';
const SESSION_EXPIRED = 'Your session has expired. Please sign in again.';
const CREATE_CHAT_TIMEOUT_MS = 15_000;

/** A failed request, with the HTTP status when the server answered. */
export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const httpError = (resp: Response, action: string): ApiError =>
  new ApiError(resp.status === 401 ? SESSION_EXPIRED : `${action} (HTTP ${resp.status}).`, resp.status);

// fetch() rejects with a bare "Failed to fetch" when the backend is down; surface the real cause.
// A caller's own abort (Stop button) is passed through unchanged so it can be told apart.
const fetchBackend = async (url: string, init?: RequestInit): Promise<Response> => {
  try {
    return await fetch(url, init);
  } catch (err) {
    if (init?.signal?.aborted) {
      if ((init.signal.reason as Error | undefined)?.name === 'TimeoutError') throw new ApiError(SERVER_TIMEOUT);
      throw err;
    }
    throw new ApiError(SERVER_UNREACHABLE);
  }
};

// Auth API
export const apiRegister = async (name: string, email: string, password: string) => {
  const resp = await fetchBackend(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Registration failed');
  }
  return resp.json();
};

export const apiLogin = async (email: string, password: string) => {
  const resp = await fetchBackend(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Invalid email or password');
  }
  return resp.json();
};

export const apiAdminLogin = async (email: string, password: string) => {
  const resp = await fetchBackend(`${API_BASE_URL}/auth/admin-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Invalid administrator email or password');
  }
  return resp.json();
};


export const apiGetMe = async (): Promise<User> => {
  const resp = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    throw new ApiError('Unauthorized', resp.status);
  }
  return resp.json();
};

// Chats API
export const apiGetChats = async (search?: string): Promise<Chat[]> => {
  const url = new URL(`${API_BASE_URL}/chats`);
  if (search) url.searchParams.append('search', search);

  const resp = await fetch(url.toString(), {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) throw new Error('Failed to load chats');
  return resp.json();
};

export const apiCreateChat = async (title?: string): Promise<Chat> => {
  const resp = await fetchBackend(`${API_BASE_URL}/chats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ title: title || 'New SAP Chat' }),
    signal: AbortSignal.timeout(CREATE_CHAT_TIMEOUT_MS),
  });
  if (!resp.ok) throw httpError(resp, 'Could not start a new chat');
  return resp.json();
};

export const apiGetChat = async (chatId: string): Promise<Chat & { messages: Message[] }> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) throw new Error('Chat not found');
  return resp.json();
};

export const apiUpdateChat = async (chatId: string, title: string): Promise<Chat> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) throw new Error('Failed to update chat');
  return resp.json();
};

export const apiDeleteChat = async (chatId: string): Promise<void> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  if (!resp.ok) throw new Error('Failed to delete chat');
};

// Messages API
export const apiGetMessages = async (chatId: string): Promise<Message[]> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) throw new Error('Failed to load messages');
  return resp.json();
};

export const apiExtractDocument = async (file: File): Promise<{
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number;
  char_count: number;
  preview: string;
  text: string;
  detected_question?: string | null;
  analysis_method?: 'vision' | 'vision+ocr' | 'ocr' | null;
}> => {
  const formData = new FormData();
  formData.append('file', file);
  const headers = authHeaders();
  // Ensure browser sets multipart/form-data boundary automatically
  delete (headers as Record<string, string>)['Content-Type'];

  const resp = await fetch(`${API_BASE_URL}/chats/extract-document`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to extract document (${resp.statusText})`);
  }
  return resp.json();
};

export const apiSendMessage = async (
  chatId: string,
  content: string,
  attachments?: DocumentAttachment[]
): Promise<Message> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      content,
      attachments: attachments && attachments.length > 0 ? attachments : undefined
    }),
  });
  if (!resp.ok) throw new Error('Failed to send message');
  return resp.json();
};

export const apiSavePartialMessage = async (chatId: string, content: string): Promise<void> => {
  try {
    await fetch(`${API_BASE_URL}/chats/${chatId}/messages/save-partial`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ content }),
    });
  } catch (err) {
    console.error('Failed to save partial message:', err);
  }
};

/** Saves a thumbs up/down on an answer; null clears it. */
export const apiSetFeedback = async (chatId: string, messageId: string, value: MessageFeedback | null): Promise<void> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages/${messageId}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ value }),
  });
  if (!resp.ok) throw new Error('Could not save feedback');
};

/** Creates (or refreshes) the public link for one prompt or answer and returns its token. */
export const apiSharePrompt = async (chatId: string, messageId: string): Promise<string> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages/${messageId}/share`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error('Could not create share link');
  return (await resp.json()).token;
};

/** Public: no login needed to read a shared prompt (and its answer, when an answer was shared). */
export const apiGetSharedPrompt = async (
  token: string
): Promise<{ content: string; answer: string | null; created_at: string }> => {
  const resp = await fetch(`${API_BASE_URL}/shared/prompts/${encodeURIComponent(token)}`);
  if (!resp.ok) throw new Error('Shared prompt not found');
  return resp.json();
};

// SSE Streaming
export interface StreamStatus {
  type: 'status';
  stage: 'thinking' | 'retrieval' | 'reranking' | 'grounding' | 'generation' | 'document_analysis' | string;
  message: string;
}

export interface StreamMetadata {
  message_id?: string;
  source_type?: 'knowledge_base' | 'github_repo' | 'web' | 'combined' | 'abstention' | 'insufficient' | 'refusal' | 'error' | 'interrupted' | 'attached_document';
  grounding_score?: number;
  citations?: Citation[];
  web_sources?: WebSource[];
  images?: WebImage[];
  is_in_rag_pipeline?: boolean;
  kb_score?: number;
  web_score?: number;
  winning_score?: number;
  source_scores?: Record<string, number>;
  comparison_audit?: Record<string, unknown>;
  verification_status?: 'verified' | 'partial' | 'unverified' | 'abstention';
  internal_evidence_confidence?: number;
  selected_evidence_quality?: number;
  external_search_used?: boolean;
  follow_up_questions?: string[];
  full_answer?: string;
}

export interface StreamCallbacks {
  onStatus?: (status: StreamStatus) => void;
  onMetadata?: (meta: StreamMetadata) => void;
  onToken?: (token: string) => void;
  onDone?: (meta: StreamMetadata, fullAnswer?: string) => void;
  onError?: (err: any) => void;
  /** Stored id of the prompt that this stream answers. */
  onUserMessage?: (messageId: string) => void;
}

export const apiStreamMessage = (
  chatId: string,
  content: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  attachments?: DocumentAttachment[]
): Promise<void> =>
  streamSSE(
    `${API_BASE_URL}/chats/${chatId}/messages?stream=true`,
    { content, attachments: attachments && attachments.length > 0 ? attachments : undefined },
    callbacks,
    signal
  );

/** Replaces a stored prompt, drops every later message, and streams the new answer. */
export const apiEditMessageStream = (
  chatId: string,
  messageId: string,
  content: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> =>
  streamSSE(`${API_BASE_URL}/chats/${chatId}/messages/${messageId}/edit`, { content }, callbacks, signal);

// The backend sends the response headers at once and then an event at every pipeline stage, so this
// much silence means the connection is stuck (e.g. a hung dev server), not that the answer is slow.
const STREAM_CONNECT_TIMEOUT_MS = 30_000;
const STREAM_IDLE_TIMEOUT_MS = 120_000;

/**
 * Posts a question and reads the SSE answer. Always ends in exactly one of onDone or onError,
 * except when the caller aborts (Stop), which ends silently.
 */
export const streamSSE = async (
  url: string,
  body: Record<string, unknown>,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> => {
  // Aborted by the caller's signal or by the watchdog when the server goes quiet.
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener('abort', forwardAbort);

  let timedOut = false;
  let watchdog: ReturnType<typeof setTimeout> | undefined;
  const expectDataWithin = (ms: number) => {
    clearTimeout(watchdog);
    watchdog = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, ms);
  };

  let isCompleted = false;

  try {
    expectDataWithin(STREAM_CONNECT_TIMEOUT_MS);
    const resp = await fetchBackend(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!resp.ok) {
      throw httpError(resp, 'The server could not answer this question');
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error('ReadableStream not supported');

    const decoder = new TextDecoder();
    let buffer = '';
    let finalReceivedAnswer: string | undefined = undefined;
    let lastDoneMeta: StreamMetadata = {};

    const finishStream = (meta?: StreamMetadata, fullAnswer?: string) => {
      if (!isCompleted) {
        isCompleted = true;
        const effectiveMeta = meta || lastDoneMeta;
        callbacks.onDone?.(effectiveMeta, fullAnswer || finalReceivedAnswer);
      }
    };

    const processBlock = (block: string) => {
      const trimmed = block.trim();
      if (!trimmed) return;

      const lines = trimmed.split('\n');
      for (const line of lines) {
        if (isCompleted) return;
        const trimmedLine = line.trim();
        if (trimmedLine.startsWith('data:')) {
          const rawData = trimmedLine.slice(5).trim();
          if (!rawData) continue;

          try {
            const parsed = JSON.parse(rawData);

            if (parsed.type === 'status') {
              callbacks.onStatus?.(parsed as StreamStatus);
            } else if (parsed.type === 'token') {
              const tokenContent = parsed.content ?? parsed.token ?? '';
              if (tokenContent) {
                callbacks.onToken?.(tokenContent);
              }
            } else if (parsed.type === 'done') {
              lastDoneMeta = parsed;
              const ans = parsed.answer || parsed.full_answer;
              if (ans) {
                finalReceivedAnswer = ans;
              }
              finishStream(parsed, ans);
            } else if (parsed.type === 'error') {
              // The backend ends the stream after an error event; nothing after it is an answer.
              isCompleted = true;
              callbacks.onError?.(new Error(parsed.message || 'Generation error occurred'));
            } else if (parsed.type === 'user_message') {
              callbacks.onUserMessage?.(parsed.message_id);
            } else if (parsed.citations !== undefined || parsed.message_id !== undefined) {
              lastDoneMeta = { ...lastDoneMeta, ...parsed };
              callbacks.onMetadata?.(parsed);
            }
          } catch (e) {
            console.error('SSE JSON parse error:', e, rawData);
          }
        }
      }
    };

    while (true) {
      expectDataWithin(STREAM_IDLE_TIMEOUT_MS);
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          processBlock(buffer);
          buffer = '';
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const normalized = buffer.replace(/\r\n/g, '\n');
      const blocks = normalized.split('\n\n');
      buffer = blocks.pop() || '';

      for (const block of blocks) {
        processBlock(block);
      }
    }

    // The backend always ends with a done or error event; closing without one means it was cut off.
    if (!isCompleted) {
      isCompleted = true;
      callbacks.onError?.(new Error('The answer was cut off before it finished. Please try again.'));
    }
  } catch (err: any) {
    if (isCompleted) return;
    isCompleted = true;
    if (timedOut) {
      callbacks.onError?.(new ApiError(SERVER_TIMEOUT));
      return;
    }
    if (signal?.aborted || err?.name === 'AbortError') {
      console.log('Streaming aborted by user.');
      return;
    }
    callbacks.onError?.(err);
  } finally {
    clearTimeout(watchdog);
    signal?.removeEventListener('abort', forwardAbort);
  }
};

// ==========================================
// Document Management & Processing API
// ==========================================

export const apiGetDocuments = async (params?: {
  status?: string;
  search?: string;
  page?: number;
  page_size?: number;
}): Promise<DocumentListResponse> => {
  const url = new URL(`${API_BASE_URL}/documents`);
  if (params?.status && params.status !== 'all') {
    url.searchParams.append('status', params.status);
  }
  if (params?.search) {
    url.searchParams.append('search', params.search);
  }
  if (params?.page) {
    url.searchParams.append('page', params.page.toString());
  }
  if (params?.page_size) {
    url.searchParams.append('page_size', params.page_size.toString());
  }

  const resp = await fetch(url.toString(), {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch knowledge base documents');
  }
  return resp.json();
};

export const apiGetDocumentDetails = async (documentId: string): Promise<any> => {
  const resp = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch document details');
  }
  return resp.json();
};

export const apiUploadDocuments = async (files: File[]): Promise<{
  status: string;
  registered_count: number;
  documents: any[];
  errors: any[];
}> => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  const resp = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: formData,
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to upload documents');
  }
  return resp.json();
};

export const apiProcessAllDocuments = async (force: boolean = false): Promise<{
  status: string;
  message: string;
}> => {
  const resp = await fetch(`${API_BASE_URL}/documents/process-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ force }),
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to trigger batch document processing');
  }
  return resp.json();
};

export const apiProcessIndividualDocument = async (
  documentId: string,
  force: boolean = true
): Promise<{ status: string; message: string }> => {
  const resp = await fetch(`${API_BASE_URL}/documents/${documentId}/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ force }),
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to process document');
  }
  return resp.json();
};

export const apiGetProcessingStatus = async (): Promise<ProcessingProgress> => {
  const resp = await fetch(`${API_BASE_URL}/documents/processing-status`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch processing status');
  }
  return resp.json();
};

export const apiDeleteDocument = async (documentId: string): Promise<{
  success: boolean;
  deleted_document_id: string;
  deleted_filename: string;
  deleted_chunks: number;
  file_deleted_from_disk: boolean;
  vector_database_status: string;
}> => {
  const resp = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to delete document');
  }
  return resp.json();
};

export const connectProcessingStream = (
  onProgress: (progress: ProcessingProgress) => void,
  onError?: (error: any) => void
): (() => void) => {
  const controller = new AbortController();
  void (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/documents/processing-stream`, {
        headers: authHeaders(), signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(`Stream request failed (${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() || '';
        for (const frame of frames) {
          const data = frame.split(/\r?\n/).filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trim()).join('\n');
          if (data) onProgress(JSON.parse(data));
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) onError?.(error);
    }
  })();
  return () => controller.abort();
};

export interface SystemConfig {
  embedding_model: string;
  embedding_dim: number;
  llm_provider: string;
  llm_model: string;
  similarity_threshold: number;
  internal_evidence_threshold: number;
  grounding_threshold: number;
  admin_api_key_enabled: boolean;
  signed_in_admin: string;
}

/** Admin only: the live model and threshold settings shown on the System tab. */
export const apiGetSystemConfig = async (): Promise<SystemConfig> => {
  const resp = await fetch(`${API_BASE_URL}/rag-inspect/system-config`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to load system configuration');
  }
  return resp.json();
};

export const apiGetRAGInspectionDocuments = async (): Promise<any> => {
  const resp = await fetch(`${API_BASE_URL}/rag-inspect/documents`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch knowledge base inspection status');
  }
  return resp.json();
};

export const apiTestSimilaritySearch = async (
  query: string,
  top_k: number = 10,
  include_web_search: boolean = false
): Promise<any> => {
  const resp = await fetch(`${API_BASE_URL}/rag-inspect/similarity-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ query, top_k, include_web_search }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to run similarity search inspection');
  }
  return resp.json();
};

export const apiTriggerIngest = async (): Promise<any> => {
  const resp = await fetch(`${API_BASE_URL}/admin/documents/ingest`, {
    method: 'POST',
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to trigger document ingestion');
  }
  return resp.json();
};


