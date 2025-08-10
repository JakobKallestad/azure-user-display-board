import { API_BASE_URL, ENDPOINTS } from '@/config/constants';
import { FileTreeResponse, ConversionRequest, ConversionResponse, ProgressInfo } from '@/types';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

const handleResponse = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorData.detail || `HTTP ${response.status}`);
  }
  return response.json();
};

class ApiService {
  private getHeaders(sessionId?: string): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }
    
    return headers;
  }

  async fetchFileTree(itemId: string, token: string): Promise<FileTreeResponse> {
    const response = await fetch(
      `${API_BASE_URL}/items/${itemId}/tree?token=${token}`,
      {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}` }
      }
    );
    return handleResponse<FileTreeResponse>(response);
  }

  async fetchFileTreeByPath(path: string, token: string): Promise<FileTreeResponse> {
    const url = new URL(`${API_BASE_URL}/path/tree`);
    url.searchParams.set('path', path);
    url.searchParams.set('token', token);
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    return handleResponse<FileTreeResponse>(response);
  }

  async startConversion(data: { 
    file_ids: string[]; 
    refresh_token: string; 
    user_id: string;
    estimated_cost?: number;
  }, sessionId?: string): Promise<{ task_id: string; session_id: string }> {
    const response = await fetch(`${API_BASE_URL}/convert`, {
      method: 'POST',
      headers: this.getHeaders(sessionId),
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to start conversion');
    }

    return response.json();
  }

  async getProgress(taskId: string, sessionId?: string): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, {
      headers: this.getHeaders(sessionId),
    });

    if (!response.ok) {
      throw new Error('Failed to get progress');
    }

    return response.json();
  }
}

export const apiService = new ApiService(); 