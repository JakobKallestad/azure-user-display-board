import { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const useSession = () => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const createNewSession = useCallback(async () => {
    try {
      setIsCreatingSession(true);
      setSessionError(null);
      console.log('Creating new session...', { API_BASE_URL });
      
      const response = await fetch(`${API_BASE_URL}/session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      console.log('Session creation response:', response.status, response.statusText);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Session creation failed:', errorText);
        throw new Error(`Failed to create session: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      const newSessionId = data.session_id;
      
      console.log('New session created:', newSessionId);
      setSessionId(newSessionId);
      localStorage.setItem('user_session_id', newSessionId);
    } catch (error) {
      console.error('Error creating session:', error);
      setSessionError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsCreatingSession(false);
    }
  }, []);

  // Get session from localStorage or create new one
  useEffect(() => {
    const storedSessionId = localStorage.getItem('user_session_id');
    console.log('Stored session ID:', storedSessionId);
    
    if (storedSessionId) {
      setSessionId(storedSessionId);
    } else {
      createNewSession();
    }
  }, [createNewSession]);

  const clearSession = useCallback(async () => {
    if (sessionId) {
      try {
        await fetch(`${API_BASE_URL}/session/${sessionId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
        });
      } catch (error) {
        console.error('Error deleting session:', error);
      }
    }
    
    setSessionId(null);
    localStorage.removeItem('user_session_id');
  }, [sessionId]);

  return {
    sessionId,
    isCreatingSession,
    sessionError,
    createNewSession,
    clearSession,
  };
}; 