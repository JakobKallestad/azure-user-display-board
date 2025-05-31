export interface FileItem {
  id: string;
  name: string;
  type: 'file' | 'folder';
  size: number;
  path: string;
  children: FileItem[];
  vob_count: number;
  is_vob: boolean;
}

export interface FileTreeResponse {
  tree: FileItem[];
  total_vob_files: number;
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
}

export interface ConversionResponse {
  task_id: string;
  message: string;
} 