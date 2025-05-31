import { useState, useEffect } from 'react';
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { toast } from "@/components/ui/sonner";
import { useAuth } from '@/context/AuthContext';

interface ProgressInfo {
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
  active_downloads?: Record<string, number>;
  active_conversions?: Record<string, number>;
  active_uploads?: Record<string, number>;
  completed_downloads?: string[];
  completed_conversions?: string[];
  completed_uploads?: string[];
  failed_files?: string[];
}

interface FileTreeItem {
  id: string;
  name: string;
  type: 'file' | 'folder';
  size: number;
  path: string;
  children: FileTreeItem[];
  vob_count: number;
  is_vob: boolean;
}

interface FileTreeResponse {
  tree: FileTreeItem[];
  total_vob_files: number;
}

const UserProfile = () => {
  const { session, refreshAccessToken } = useAuth();
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fileTree, setFileTree] = useState<FileTreeItem[]>([]);
  const [totalVobFiles, setTotalVobFiles] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [progressInfo, setProgressInfo] = useState<ProgressInfo | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [onedriveUrl, setOnedriveUrl] = useState('');
  const [isConverting, setIsConverting] = useState(false);
  const [isLoadingTree, setIsLoadingTree] = useState(false);

  useEffect(() => {
    fetchUserData();
  }, []);

  const fetchUserData = async () => {
    try {
      setLoading(true);
      const providerToken = session?.provider_token;
      if (!providerToken) throw new Error('No provider token available');

      const response = await fetch('https://graph.microsoft.com/v1.0/me', {
        headers: { 'Authorization': `Bearer ${providerToken}` }
      });

      if (!response.ok) throw new Error(`Graph API returned ${response.status}`);
      const data = await response.json();
      setUserData(data);
    } catch (error) {
      console.error('Error fetching user data:', error);
      toast.error(error.message || 'Failed to load your profile');
    } finally {
      setLoading(false);
    }
  };

  const fetchFileTree = async () => {
    try {
      setIsLoadingTree(true);
      const providerToken = session?.provider_token;
      if (!providerToken) throw new Error('No provider token available');

      // Extract item_id from the OneDrive URL
      let itemId = null;
      if (onedriveUrl) {
        const parsed = new URL(onedriveUrl);
        itemId = parsed.searchParams.get('id');
      }
      
      if (!itemId) {
        toast.error('Please enter a valid OneDrive URL with an item ID');
        return;
      }

      const response = await fetch(`http://localhost:7000/items/${itemId}/tree?token=${providerToken}`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${providerToken}` }
      });

      if (!response.ok) {
        if (response.status === 401) {
          await refreshAccessToken();
          const newToken = session?.provider_token;
          if (newToken) {
            const retryResponse = await fetch(`http://localhost:7000/items/${itemId}/tree?token=${newToken}`, {
              method: 'GET',
              headers: { 'Authorization': `Bearer ${newToken}` }
            });
            if (!retryResponse.ok) throw new Error(`Failed to fetch file tree: ${retryResponse.status}`);
            const retryData: FileTreeResponse = await retryResponse.json();
            setFileTree(retryData.tree);
            setTotalVobFiles(retryData.total_vob_files);
            
            // Auto-select all VOB files and expand folders containing them
            const { selectedVobFiles, foldersToExpand } = processFileTree(retryData.tree);
            setSelectedFiles(selectedVobFiles);
            setExpandedFolders(foldersToExpand);
            return;
          }
        }
        throw new Error(`Failed to fetch file tree: ${response.status}`);
      }

      const data: FileTreeResponse = await response.json();
      setFileTree(data.tree);
      setTotalVobFiles(data.total_vob_files);
      
      // Auto-select all VOB files and expand folders containing them
      const { selectedVobFiles, foldersToExpand } = processFileTree(data.tree);
      setSelectedFiles(selectedVobFiles);
      setExpandedFolders(foldersToExpand);
      
      toast.success(`Found ${data.total_vob_files} VOB files in the folder structure`);
    } catch (error) {
      console.error('Error fetching file tree:', error);
      toast.error(error.message || 'Failed to load folder structure');
    } finally {
      setIsLoadingTree(false);
    }
  };

  const processFileTree = (items: FileTreeItem[]): { selectedVobFiles: Set<string>, foldersToExpand: Set<string> } => {
    const selectedVobFiles = new Set<string>();
    const foldersToExpand = new Set<string>();

    const processItem = (item: FileTreeItem): boolean => {
      let hasVobFiles = false;

      if (item.type === 'file' && item.is_vob) {
        selectedVobFiles.add(item.id);
        hasVobFiles = true;
      } else if (item.type === 'folder') {
        for (const child of item.children) {
          if (processItem(child)) {
            hasVobFiles = true;
          }
        }
        if (hasVobFiles) {
          foldersToExpand.add(item.id);
        }
      }

      return hasVobFiles;
    };

    items.forEach(processItem);
    return { selectedVobFiles, foldersToExpand };
  };

  const toggleFileSelection = (fileId: string) => {
    const newSelected = new Set(selectedFiles);
    if (newSelected.has(fileId)) {
      newSelected.delete(fileId);
    } else {
      newSelected.add(fileId);
    }
    setSelectedFiles(newSelected);
  };

  const toggleFolderExpansion = (folderId: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(folderId)) {
      newExpanded.delete(folderId);
    } else {
      newExpanded.add(folderId);
    }
    setExpandedFolders(newExpanded);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const renderFileTreeItem = (item: FileTreeItem, depth: number = 0): JSX.Element => {
    const isExpanded = expandedFolders.has(item.id);
    const isSelected = selectedFiles.has(item.id);
    const indentStyle = { paddingLeft: `${depth * 20 + 8}px` };

    return (
      <div key={item.id} className="border-b border-gray-100 last:border-b-0">
        <div 
          className={`flex items-center py-2 px-2 hover:bg-gray-50 ${
            item.is_vob ? 'bg-blue-50' : ''
          }`}
          style={indentStyle}
        >
          {/* Checkbox */}
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => toggleFileSelection(item.id)}
            className="mr-3 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
            disabled={item.type === 'folder'}
          />

          {/* Folder expand/collapse button */}
          {item.type === 'folder' && (
            <button
              onClick={() => toggleFolderExpansion(item.id)}
              className="mr-2 p-1 hover:bg-gray-200 rounded"
            >
              {isExpanded ? '📂' : '📁'}
            </button>
          )}

          {/* File/Folder icon and name */}
          <div className="flex items-center flex-1 min-w-0">
            <span className="mr-2">
              {item.type === 'file' ? (item.is_vob ? '🎬' : '📄') : ''}
            </span>
            <span className={`truncate ${item.is_vob ? 'font-semibold text-blue-800' : ''}`}>
              {item.name}
            </span>
            {item.type === 'folder' && item.vob_count > 0 && (
              <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full">
                {item.vob_count} VOB
              </span>
            )}
          </div>

          {/* File size */}
          {item.type === 'file' && (
            <span className="text-sm text-gray-500 ml-2">
              {formatFileSize(item.size)}
            </span>
          )}
        </div>

        {/* Render children if folder is expanded */}
        {item.type === 'folder' && isExpanded && item.children.length > 0 && (
          <div>
            {item.children.map(child => renderFileTreeItem(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const handleConvert = async () => {
    if (selectedFiles.size === 0) {
      toast.error('Please select at least one VOB file to convert');
      return;
    }

    try {
      setIsConverting(true);
      const refreshToken = session?.provider_refresh_token;

      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const response = await fetch('http://localhost:7000/convert', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          file_ids: Array.from(selectedFiles),
          refresh_token: refreshToken
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Conversion failed');
      }

      const data = await response.json();
      setTaskId(data.task_id);
      toast.success(`Conversion started for ${selectedFiles.size} files!`);
      
      // Start polling for progress
      pollProgress(data.task_id);
    } catch (error) {
      console.error('Error starting conversion:', error);
      toast.error(error.message || 'Failed to start conversion');
      setIsConverting(false);
    }
  };

  const handleSignOut = async () => {
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      toast.success('Signed out successfully');
    } catch (error) {
      console.error('Error signing out:', error);
      toast.error('Failed to sign out');
    }
  };

  const getPhaseDisplayName = (phase: string) => {
    const phaseNames = {
      'initializing': 'Initializing',
      'discovering': 'Finding Files',
      'downloading': 'Downloading',
      'converting': 'Converting',
      'uploading': 'Uploading',
      'completed': 'Completed'
    };
    return phaseNames[phase] || phase;
  };

  const getPhaseColor = (phase: string) => {
    const colors = {
      'initializing': 'bg-gray-500',
      'discovering': 'bg-blue-500',
      'downloading': 'bg-green-500',
      'converting': 'bg-yellow-500',
      'uploading': 'bg-purple-500',
      'completed': 'bg-emerald-500'
    };
    return colors[phase] || 'bg-gray-500';
  };

  const pollProgress = async (taskId: string) => {
    const poll = async () => {
      try {
        const response = await fetch(`http://localhost:7000/progress/${taskId}`);
        if (response.ok) {
        const data = await response.json();
          setProgressInfo(data);

          if (data.current_phase === 'completed' || data.overall_progress >= 100) {
            setIsConverting(false);
          toast.success('Conversion completed!');
            return;
          }
        }
      } catch (error) {
        console.error('Error polling progress:', error);
      }
      
      // Continue polling every 2 seconds
      setTimeout(poll, 2000);
    };
    
    poll();
  };

  // Add this helper function to display active operations
  const renderActiveOperations = (progressInfo: ProgressInfo) => {
    const operations = [];
    
    if (progressInfo.active_downloads && Object.keys(progressInfo.active_downloads).length > 0) {
      operations.push(
        <div key="downloads" className="mb-2">
          <span className="text-xs font-medium text-blue-600">⬇️ Downloading:</span>
          {Object.entries(progressInfo.active_downloads).map(([filename, progress]) => (
            <div key={filename} className="ml-4 mb-1">
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-600 truncate">{filename}</span>
                <span className="text-xs text-gray-500">{progress}%</span>
              </div>
              <Progress value={progress} className="h-1" />
            </div>
          ))}
        </div>
      );
    }
    
    if (progressInfo.active_conversions && Object.keys(progressInfo.active_conversions).length > 0) {
      operations.push(
        <div key="conversions" className="mb-2">
          <span className="text-xs font-medium text-orange-600">🔄 Converting:</span>
          {Object.entries(progressInfo.active_conversions).map(([filename, progress]) => (
            <div key={filename} className="ml-4 mb-1">
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-600 truncate">{filename}</span>
                <span className="text-xs text-gray-500">{progress}%</span>
              </div>
              <Progress value={progress} className="h-1" />
            </div>
          ))}
        </div>
      );
    }
    
    if (progressInfo.active_uploads && Object.keys(progressInfo.active_uploads).length > 0) {
      operations.push(
        <div key="uploads" className="mb-2">
          <span className="text-xs font-medium text-green-600">⬆️ Uploading:</span>
          {Object.entries(progressInfo.active_uploads).map(([filename, progress]) => (
            <div key={filename} className="ml-4 mb-1">
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-600 truncate">{filename}</span>
                <span className="text-xs text-gray-500">{progress}%</span>
              </div>
              <Progress value={progress} className="h-1" />
            </div>
          ))}
        </div>
      );
    }
    
    return operations;
  };

  // Update the helper functions for better display
  const getPhaseLabel = (phase: string) => {
    switch (phase) {
      case "downloading": return "Files Downloaded";
      case "converting": return "Files Converted";
      case "uploading": return "Files Uploaded";
      default: return "Files Processed";
    }
  };

  const renderCompletedSummary = (progressInfo: ProgressInfo) => {
    const totalFiles = progressInfo.total_files
    
    const completed = [
      { 
        label: "Downloaded", 
        count: progressInfo.completed_downloads?.length || 0, 
        total: totalFiles,
        color: "text-blue-600" 
      },
      { 
        label: "Converted", 
        count: progressInfo.completed_conversions?.length || 0, 
        total: totalFiles,
        color: "text-orange-600" 
      },
      { 
        label: "Uploaded", 
        count: progressInfo.completed_uploads?.length || 0, 
        total: totalFiles,
        color: "text-green-600" 
      },
    ];
    
    const failed = progressInfo.failed_files?.length || 0;
    
    return (
      <div className="space-y-3">
        {completed.map(({ label, count, total, color }) => (
          <div key={label} className="flex items-center justify-between">
            <span className={`font-medium ${color}`}>{label}:</span>
            <div className="flex items-center space-x-2">
              <span className="text-lg font-bold">{count} / {total}</span>
              <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className={`h-full transition-all duration-300 ${
                    color.includes('blue') ? 'bg-blue-500' :
                    color.includes('orange') ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: total > 0 ? `${(count / total) * 100}%` : '0%' }}
                />
              </div>
            </div>
          </div>
        ))}
        {failed > 0 && (
          <div className="flex items-center justify-between pt-2 border-t">
            <span className="font-medium text-red-600">Failed:</span>
            <span className="text-lg font-bold text-red-600">{failed}</span>
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return <div>Loading your profile...</div>;
  }

  return (
    <div className="w-full space-y-4">
      {/* Compressed top section with User Profile and Convert VOB Files side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">User Profile</CardTitle>
              <Button onClick={handleSignOut} size="sm">Sign Out</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-600">Display Name</div>
              <div className="text-sm font-semibold">{userData?.displayName || 'Loading...'}</div>
            </div>
            
            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-600">Email</div>
              <div className="text-sm font-mono text-gray-700">{userData?.mail || userData?.userPrincipalName || 'Loading...'}</div>
            </div>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Convert VOB Files</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">OneDrive Folder URL</label>
              <input
                type="text"
                value={onedriveUrl}
                onChange={(e) => setOnedriveUrl(e.target.value)}
                placeholder="Paste your OneDrive folder URL here..."
                className="w-full p-2 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            
            <div className="flex space-x-2">
              <Button 
                onClick={fetchFileTree}
                disabled={!onedriveUrl.trim() || isLoadingTree}
                className="flex-1"
                size="sm"
              >
                {isLoadingTree ? 'Loading...' : 'Load Structure'}
              </Button>
              
              <Button 
                onClick={handleConvert}
                disabled={!onedriveUrl.trim() || selectedFiles.size === 0 || isConverting}
                variant="default"
                className="flex-1"
                size="sm"
              >
                {isConverting ? 'Converting...' : `Convert (${selectedFiles.size})`}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Expanded File Tree Section */}
      {fileTree.length > 0 && (
        <Card className="w-full">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-xl">
              <span>Folder Structure</span>
              <div className="text-sm font-normal text-gray-600">
                {totalVobFiles} VOB files found • {selectedFiles.size} selected
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="h-96 lg:h-[500px] xl:h-[600px] overflow-y-auto border border-gray-200 rounded-lg">
              {fileTree.map(item => renderFileTreeItem(item))}
            </div>
            
            {selectedFiles.size > 0 && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="text-sm font-medium text-blue-800">
                  {selectedFiles.size} files selected for conversion
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Enhanced Progress Display */}
      {progressInfo && (
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>File Conversion Progress</span>
              <span className="text-sm font-normal text-gray-500 capitalize">
                {progressInfo.current_phase}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Overall Progress */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-lg font-semibold">Overall Progress</span>
                <span className="text-lg font-bold text-blue-600">
                  {progressInfo.overall_progress}%
                </span>
              </div>
              <Progress value={progressInfo.overall_progress} className="h-3" />
            </div>

            {/* Current Phase Progress */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-base font-medium">
                  {getPhaseLabel(progressInfo.current_phase)}
                </span>
                <span className="text-base font-semibold">
                  {progressInfo.files_completed} / {progressInfo.total_files}
                </span>
              </div>
              <Progress 
                value={progressInfo.total_files > 0 ? (progressInfo.files_completed / progressInfo.total_files) * 100 : 0} 
                className="h-2" 
              />
            </div>

            {/* Time Estimates */}
            {(progressInfo.estimated_phase_time_remaining || progressInfo.estimated_time_remaining) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {progressInfo.estimated_phase_time_remaining && (
                  <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg">
                    <div className="text-xs font-medium text-blue-800 uppercase tracking-wide">
                      Current Phase Time Remaining
                    </div>
                    <div className="text-lg font-bold text-blue-900">
                      {progressInfo.estimated_phase_time_remaining}
                    </div>
                  </div>
                )}
                {progressInfo.estimated_time_remaining && progressInfo.current_phase !== "uploading" && (
                  <div className="bg-gray-50 border border-gray-200 p-3 rounded-lg">
                    <div className="text-xs font-medium text-gray-800 uppercase tracking-wide">
                      Total Process Time Remaining
                    </div>
                    <div className="text-lg font-bold text-gray-900">
                      {progressInfo.estimated_time_remaining}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Progress Summary - Made much bigger and prominent */}
            {(progressInfo.completed_downloads || progressInfo.completed_conversions || progressInfo.completed_uploads) && (
              <div className="bg-gradient-to-r from-gray-50 to-gray-100 border border-gray-200 p-4 rounded-lg">
                <h3 className="text-lg font-semibold mb-4 text-gray-800">Progress Summary</h3>
                {renderCompletedSummary(progressInfo)}
              </div>
            )}

            {/* Current Activity */}
            {progressInfo.current_file && (
              <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg">
                <div className="text-sm font-medium text-blue-800 mb-1">Currently Processing:</div>
                <div className="text-sm text-blue-700 font-mono truncate">
                  {progressInfo.current_file}
                </div>
              </div>
            )}

            {/* Details */}
            {progressInfo.details && (
              <div className="bg-gray-50 border border-gray-200 p-3 rounded-lg">
                <div className="text-sm text-gray-700">{progressInfo.details}</div>
              </div>
            )}

            {/* Active Operations - Collapsible */}
            {(progressInfo.active_downloads || progressInfo.active_conversions || progressInfo.active_uploads) && (
              <details className="bg-white border border-gray-200 rounded-lg">
                <summary className="p-3 cursor-pointer font-medium text-gray-700 hover:bg-gray-50 rounded-lg">
                  Active Operations ({
                    Object.keys(progressInfo.active_downloads || {}).length +
                    Object.keys(progressInfo.active_conversions || {}).length +
                    Object.keys(progressInfo.active_uploads || {}).length
                  } files)
                </summary>
                <div className="p-3 pt-0 max-h-40 overflow-y-auto">
                  {renderActiveOperations(progressInfo)}
                </div>
              </details>
            )}

            {/* Failed Files */}
            {progressInfo.failed_files && progressInfo.failed_files.length > 0 && (
              <div className="bg-red-50 border border-red-200 p-4 rounded-lg">
                <h3 className="text-lg font-semibold text-red-800 mb-3">
                  Failed Operations ({progressInfo.failed_files.length})
                </h3>
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {progressInfo.failed_files.map((error, index) => (
                    <div key={index} className="text-sm text-red-700 font-mono bg-white p-2 rounded border">
                      {error}
                    </div>
                  ))}
                </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}
    </div>
  );
};

export default UserProfile;