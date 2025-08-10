// Backend configuration - can be switched via environment variable
const getApiBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  
  // If explicitly set, use that (this covers your local uvicorn setup)
  if (envUrl) {
    return envUrl;
  }
  
  // In development mode with Docker, use the proxy
  if (import.meta.env.DEV) {
    return '/api';
  }
  
  // Fallback
  return 'http://localhost:8000';
};

export const API_BASE_URL = getApiBaseUrl();

// For debugging - log which backend we're using
console.log('🔗 API Backend:', API_BASE_URL);

export const ENDPOINTS = {
  CONVERT: '/convert',
  PROGRESS: '/progress',
  ITEMS_TREE: (itemId: string) => `/items/${itemId}/tree`,
} as const;

export const PHASE_DISPLAY_NAMES = {
  'initializing': 'Initializing',
  'discovering': 'Finding Files',
  'downloading': 'Downloading',
  'converting': 'Converting',
  'uploading': 'Uploading',
  'completed': 'Completed'
} as const;

export const POLLING_INTERVAL = 1000; // ms

export const PROGRESS_COLORS = {
  download: 'bg-blue-500',
  convert: 'bg-orange-500',
  upload: 'bg-green-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500'
} as const; 