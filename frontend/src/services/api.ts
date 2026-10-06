import type { User, Chat, Message, Citation, WebSource } from '../types';

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

const authHeaders = (): Record<string, string> => {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// Auth API
export const apiRegister = async (name: string, email: string, password: string) => {
  const resp = await fetch(`${API_BASE_URL}/auth/register`, {
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
  const resp = await fetch(`${API_BASE_URL}/auth/login`, {
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

export const apiGetMe = async (): Promise<User> => {
  const resp = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    throw new Error('Unauthorized');
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
  const resp = await fetch(`${API_BASE_URL}/chats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ title: title || 'New SAP Chat' }),
  });
  if (!resp.ok) throw new Error('Failed to create chat');
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

export const apiSendMessage = async (chatId: string, content: string): Promise<Message> => {
  const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ content }),
  });
  if (!resp.ok) throw new Error('Failed to send message');
  return resp.json();
};

// SSE Streaming
export interface StreamMetadata {
  message_id: string;
  source_type: 'knowledge_base' | 'web' | 'refusal' | 'error';
  grounding_score: number;
  citations: Citation[];
  web_sources: WebSource[];
}

export const apiStreamMessage = async (
  chatId: string,
  content: string,
  onMetadata: (meta: StreamMetadata) => void,
  onToken: (token: string) => void,
  onDone: (fullAnswer?: string) => void,
  onError: (err: any) => void
) => {
  try {
    const resp = await fetch(`${API_BASE_URL}/chats/${chatId}/messages?stream=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({ content }),
    });

    if (!resp.ok) {
      throw new Error(`Failed to stream message: ${resp.statusText}`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error('ReadableStream not supported');

    const decoder = new TextDecoder();
    let buffer = '';

    let isCompleted = false;
    let finalReceivedAnswer: string | undefined = undefined;

    const finishStream = (fullAnswer?: string) => {
      if (!isCompleted) {
        isCompleted = true;
        onDone(fullAnswer || finalReceivedAnswer);
      }
    };

    const processBlock = (block: string) => {
      const trimmed = block.trim();
      if (!trimmed) return;
      const eventMatch = trimmed.match(/event:\s*(\w+)/);
      const dataMatch = trimmed.match(/data:\s*([\s\S]+)$/);

      if (eventMatch && dataMatch) {
        const eventType = eventMatch[1];
        const rawData = dataMatch[1].trim();

        try {
          const parsed = JSON.parse(rawData);
          if (eventType === 'metadata') {
            onMetadata(parsed);
          } else if (eventType === 'token') {
            if (parsed.token !== undefined) {
              onToken(parsed.token);
            }
          } else if (eventType === 'done') {
            if (parsed.full_answer) {
              finalReceivedAnswer = parsed.full_answer;
            }
            finishStream(parsed.full_answer);
          }
        } catch (e) {
          console.error('SSE JSON parse error:', e, rawData);
        }
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          processBlock(buffer);
          buffer = '';
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      // Standardize Windows CRLF to standard LF
      const normalized = buffer.replace(/\r\n/g, '\n');
      const blocks = normalized.split('\n\n');
      buffer = blocks.pop() || '';

      for (const block of blocks) {
        processBlock(block);
      }
    }
    finishStream();
  } catch (err) {
    onError(err);
  }
};
