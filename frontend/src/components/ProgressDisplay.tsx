import React from 'react';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ProgressInfo, FileProgress } from '@/types';
import { PHASE_DISPLAY_NAMES } from '@/config/constants';
import { 
  Clock, 
  FileVideo, 
  Download, 
  Upload, 
  Search, 
  Settings, 
  CheckCircle,
  AlertCircle,
  Loader2,
  Timer
} from 'lucide-react';

interface ProgressDisplayProps {
  progress: ProgressInfo;
}

const getPhaseIcon = (phase: string) => {
  switch (phase) {
    case 'initializing':
      return <Settings className="h-4 w-4" />;
    case 'discovering':
      return <Search className="h-4 w-4" />;
    case 'downloading':
      return <Download className="h-4 w-4" />;
    case 'converting':
      return <FileVideo className="h-4 w-4" />;
    case 'uploading':
      return <Upload className="h-4 w-4" />;
    case 'completed':
      return <CheckCircle className="h-4 w-4 text-green-500" />;
    default:
      return <Loader2 className="h-4 w-4 animate-spin" />;
  }
};

const getPhaseColor = (phase: string) => {
  switch (phase) {
    case 'completed':
      return 'bg-green-500';
    case 'converting':
      return 'bg-orange-500';
    case 'uploading':
      return 'bg-green-500';
    case 'downloading':
      return 'bg-blue-500';
    case 'discovering':
      return 'bg-yellow-500';
    case 'initializing':
      return 'bg-gray-500';
    default:
      return 'bg-blue-500';
  }
};

const getTypeColor = (type: string) => {
  switch (type) {
    case 'download':
      return 'bg-blue-500';
    case 'convert':
      return 'bg-orange-500';
    case 'upload':
      return 'bg-green-500';
    default:
      return 'bg-gray-500';
  }
};

const getTypeIcon = (type: string) => {
  switch (type) {
    case 'download':
      return <Download className="h-3 w-3" />;
    case 'convert':
      return <FileVideo className="h-3 w-3" />;
    case 'upload':
      return <Upload className="h-3 w-3" />;
    default:
      return <Loader2 className="h-3 w-3" />;
  }
};

const FileProgressBar: React.FC<{ 
  filename: string; 
  progress: number; 
  type: 'download' | 'convert' | 'upload';
}> = ({ filename, progress, type }) => {
  const progressColor = getTypeColor(type);
  const icon = getTypeIcon(type);
  
  return (
    <div className="space-y-1 p-3 bg-gray-50 rounded-lg border">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {icon}
          <span className="truncate font-medium">{filename}</span>
        </div>
        <span className="text-muted-foreground ml-2 font-mono">
          {progress}%
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
        <div 
          className={`h-full rounded-full transition-all duration-300 ${progressColor}`}
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
    </div>
  );
};

export const ProgressDisplay: React.FC<ProgressDisplayProps> = ({ progress }) => {
  const getPhaseDisplayName = (phase: string) => {
    return PHASE_DISPLAY_NAMES[phase as keyof typeof PHASE_DISPLAY_NAMES] || phase;
  };

  const isCompleted = progress.current_phase === 'completed';
  const hasError = progress.details.toLowerCase().includes('error') || progress.details.toLowerCase().includes('failed');

  // Calculate summary counts from completed arrays
  const downloadedCount = progress.completed_downloads.length;
  const convertedCount = progress.completed_conversions.length;
  const uploadedCount = progress.completed_uploads.length;
  const failedCount = progress.failed_files.length;

  // Collect all active files for display
  const activeFiles: Array<{ filename: string; progress: number; type: 'download' | 'convert' | 'upload' }> = [];

  // Add active downloads
  Object.entries(progress.active_downloads).forEach(([filename, progressValue]) => {
    activeFiles.push({ filename, progress: progressValue, type: 'download' });
  });

  // Add active conversions
  Object.entries(progress.active_conversions).forEach(([filename, progressValue]) => {
    activeFiles.push({ filename, progress: progressValue, type: 'convert' });
  });

  // Add active uploads
  Object.entries(progress.active_uploads).forEach(([filename, progressValue]) => {
    activeFiles.push({ filename, progress: progressValue, type: 'upload' });
  });

  return (
    <Card className="w-full border-2 shadow-lg">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            {getPhaseIcon(progress.current_phase)}
            <span>Conversion Progress</span>
            {isCompleted && (
              <Badge variant="default" className="bg-green-500 hover:bg-green-600">
                Complete
              </Badge>
            )}
            {hasError && failedCount > 0 && (
              <Badge variant="destructive" className="flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                Issues
              </Badge>
            )}
          </CardTitle>
          <div className="text-right">
            <div className="text-sm font-medium">
              {progress.files_completed}/{progress.total_files} files
            </div>
            <div className="text-xs text-muted-foreground">
              {progress.total_files > 0 && 
                `${Math.round((progress.files_completed / progress.total_files) * 100)}% complete`
              }
            </div>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Overall Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Overall Progress</span>
            <span className="text-muted-foreground">{progress.overall_progress}%</span>
          </div>
          <div className="relative">
            <Progress value={progress.overall_progress} className="h-3" />
            <div 
              className="absolute top-0 left-0 h-full bg-purple-500 rounded-full transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(0, progress.overall_progress))}%` }}
            />
          </div>
          {progress.estimated_time_remaining && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Timer className="h-3 w-3" />
              <span>Total time remaining:</span>
              <Badge variant="outline" className="font-mono text-xs">
                {progress.estimated_time_remaining}
              </Badge>
            </div>
          )}
        </div>

        {/* Current Phase Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">
              {getPhaseDisplayName(progress.current_phase)} Progress
            </span>
            <span className="text-muted-foreground">{progress.phase_progress}%</span>
          </div>
          <div className="relative">
            <Progress value={progress.phase_progress} className="h-3" />
            <div 
              className={`absolute top-0 left-0 h-3 rounded-full transition-all duration-300 ${getPhaseColor(progress.current_phase)}`}
              style={{ width: `${progress.phase_progress}%` }}
            />
          </div>
          {progress.estimated_phase_time_remaining && !isCompleted && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Timer className="h-3 w-3" />
              <span>Phase time remaining:</span>
              <Badge variant="outline" className="font-mono text-xs">
                {progress.estimated_phase_time_remaining}
              </Badge>
            </div>
          )}
        </div>

        {/* Progress Summary */}
        <div className="space-y-3">
          <h4 className="text-sm font-medium">Progress Summary</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center p-3 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center justify-center gap-1 text-lg font-bold text-blue-600 mb-1">
                <Download className="h-4 w-4" />
                {downloadedCount} / {progress.total_files}
              </div>
              <div className="text-xs text-blue-700 mb-2">Downloaded</div>
              <div className="w-full bg-blue-200 rounded-full h-1.5">
                <div 
                  className="h-full bg-blue-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress.total_files > 0 ? (downloadedCount / progress.total_files) * 100 : 0}%` }}
                />
              </div>
            </div>
            
            <div className="text-center p-3 bg-orange-50 rounded-lg border border-orange-200">
              <div className="flex items-center justify-center gap-1 text-lg font-bold text-orange-600 mb-1">
                <FileVideo className="h-4 w-4" />
                {convertedCount} / {progress.total_files}
              </div>
              <div className="text-xs text-orange-700 mb-2">Converted</div>
              <div className="w-full bg-orange-200 rounded-full h-1.5">
                <div 
                  className="h-full bg-orange-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress.total_files > 0 ? (convertedCount / progress.total_files) * 100 : 0}%` }}
                />
              </div>
            </div>
            
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
              <div className="flex items-center justify-center gap-1 text-lg font-bold text-green-600 mb-1">
                <Upload className="h-4 w-4" />
                {uploadedCount} / {progress.total_files}
              </div>
              <div className="text-xs text-green-700 mb-2">Uploaded</div>
              <div className="w-full bg-green-200 rounded-full h-1.5">
                <div 
                  className="h-full bg-green-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress.total_files > 0 ? (uploadedCount / progress.total_files) * 100 : 0}%` }}
                />
              </div>
            </div>

            {failedCount > 0 && (
              <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
                <div className="flex items-center justify-center gap-1 text-lg font-bold text-red-600 mb-1">
                  <AlertCircle className="h-4 w-4" />
                  {failedCount} / {progress.total_files}
                </div>
                <div className="text-xs text-red-700 mb-2">Failed</div>
                <div className="w-full bg-red-200 rounded-full h-1.5">
                  <div 
                    className="h-full bg-red-500 rounded-full transition-all duration-300"
                    style={{ width: `${progress.total_files > 0 ? (failedCount / progress.total_files) * 100 : 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Currently Processing Files */}
        {activeFiles.length > 0 && (
          <>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Currently Processing ({activeFiles.length} files)
              </h4>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {activeFiles.map(({ filename, progress: fileProgress, type }) => (
                  <FileProgressBar
                    key={`${type}-${filename}`}
                    filename={filename}
                    progress={fileProgress}
                    type={type}
                  />
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}; 