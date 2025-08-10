export interface FileItem {
  id: string;
  name: string;
  type: 'file' | 'folder';
  size: number;
  path: string;
  children: FileItem[];
  vob_count: number;
  vob_size: number;
  is_vob: boolean;
}

export interface ProcessingEstimates {
  total_size_bytes: number;
  total_size_gb: number;
  estimated_minutes: number;
  estimated_cost: number;
  total_cost_usd: number;
  can_afford?: boolean;
}

export interface FileTreeResponse {
  tree: FileItem[];
  total_vob_files: number;
  total_vob_size: number;
  estimates: ProcessingEstimates;
}

export interface FileProgress {
  progress: number;
}

export interface ProgressInfo {
  task_id: string;
  overall_progress: number;
  current_phase: string;
  phase_progress: number;
  current_file: string;
  files_completed: number;
  total_files: number;
  details: string;
  estimated_time_remaining: string;
  estimated_phase_time_remaining: string;
  active_downloads: Record<string, number>;
  active_conversions: Record<string, number>;
  active_uploads: Record<string, number>;
  completed_downloads: string[];
  completed_conversions: string[];
  completed_uploads: string[];
  failed_files: string[];
}

export interface ConversionRequest {
  file_ids: string[];
  refresh_token: string;
  user_id: string;
  estimated_cost?: number;
}

export interface ConversionResponse {
  task_id: string;
  session_id: string;
}

export interface UserCredits {
  user_id: string;
  credits: number;
  updated_at: string;
}

export interface CreditTransaction {
  user_id: string;
  previous_credits?: number;
  added_amount?: number;
  deducted_amount?: number;
  new_credits?: number;
  remaining_credits?: number;
  updated_at: string;
} 