import { useState, useCallback, useRef } from 'react';
import { ProgressInfo } from '@/types';
import { apiService } from '@/services/api';
import { useToast } from './use-toast';
import { useAuth } from './useAuth';
import { useSession } from './useSession';
import { POLLING_INTERVAL } from '@/config/constants';

export const useConversion = () => {
  const [isConverting, setIsConverting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  
  const { toast } = useToast();
  const { refreshToken } = useAuth();
  const { sessionId } = useSession();
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const pollProgress = useCallback(async (taskId: string) => {
    try {
      const progressData = await apiService.getProgress(taskId, sessionId || undefined);
      setProgress(progressData);

      if (progressData.current_phase === 'completed') {
        setIsConverting(false);
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        
        const failedCount = progressData.failed_files?.length || 0;
        if (failedCount > 0) {
          toast({
            title: "Conversion Completed with Issues",
            description: `${progressData.files_completed} files converted successfully, ${failedCount} failed`,
            variant: "destructive",
          });
        } else {
          toast({
            title: "Conversion Completed",
            description: `All ${progressData.files_completed} files converted successfully`,
          });
        }
      }
    } catch (error) {
      console.error('Error polling progress:', error);
    }
  }, [sessionId, toast]);

  const startConversion = useCallback(async (data: { 
    file_ids: string[]; 
    refresh_token: string; 
    user_id: string;
    estimated_cost?: number;
  }) => {
    if (data.file_ids.length === 0) {
      toast({
        title: "Error",
        description: "Please select at least one VOB file to convert",
        variant: "destructive",
      });
      return;
    }

    if (!data.refresh_token) {
      toast({
        title: "Error",
        description: "No refresh token available",
        variant: "destructive",
      });
      return;
    }

    if (!sessionId) {
      toast({
        title: "Error",
        description: "No session available",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsConverting(true);
      setProgress(null);

      const response = await apiService.startConversion(data, sessionId);

      setTaskId(response.task_id);
      toast({
        title: "Success",
        description: `Conversion started for ${data.file_ids.length} files!`,
      });

      // Start polling for progress
      pollIntervalRef.current = setInterval(() => {
        pollProgress(response.task_id);
      }, POLLING_INTERVAL);

    } catch (error) {
      console.error('Error starting conversion:', error);
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : 'Failed to start conversion',
        variant: "destructive",
      });
      setIsConverting(false);
      throw error; // Re-throw so UserProfile can handle it
    }
  }, [sessionId, toast, pollProgress]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const cleanup = useCallback(() => {
    stopPolling();
    setIsConverting(false);
    setTaskId(null);
    setProgress(null);
  }, [stopPolling]);

  return {
    isConverting,
    taskId,
    progress,
    startConversion,
    stopPolling,
    cleanup,
  };
}; 