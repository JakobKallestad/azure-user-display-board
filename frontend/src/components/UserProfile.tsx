import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { FileTreeItem } from './FileTreeItem';
import { ProgressDisplay } from './ProgressDisplay';
import { useAuth } from '@/hooks/useAuth';
import { useFileTree } from '@/hooks/useFileTree';
import { useConversion } from '@/hooks/useConversion';
import { useSession } from '@/hooks/useSession';
import { useToast } from '@/hooks/use-toast';
import { Loader2, FolderOpen, FileVideo, Users } from 'lucide-react';

const UserProfile: React.FC = () => {
  const [onedriveUrl, setOnedriveUrl] = useState('');
  
  const { session, signOut, loading } = useAuth();
  const { toast } = useToast();
  const { sessionId, isCreatingSession, sessionError, clearSession } = useSession();
  
  const {
    fileTree,
    totalVobFiles,
    isLoadingTree,
    selectedFiles,
    expandedFolders,
    fetchFileTree,
    toggleFileSelection,
    toggleFolderExpansion,
    selectAllVobFiles,
    clearSelection,
  } = useFileTree();

  const {
    isConverting,
    progress,
    startConversion,
    cleanup: cleanupConversion,
  } = useConversion();

  // Debug logging
  useEffect(() => {
    console.log('UserProfile state:', {
      sessionId,
      isCreatingSession,
      sessionError,
      selectedFilesCount: selectedFiles.size,
      isConverting,
      hasRefreshToken: !!session?.refresh_token
    });
  }, [sessionId, isCreatingSession, sessionError, selectedFiles.size, isConverting, session?.refresh_token]);

  // Show session error toast
  useEffect(() => {
    if (sessionError) {
      toast({
        title: "Session Error",
        description: sessionError,
        variant: "destructive",
      });
    }
  }, [sessionError, toast]);

  // Auto-scroll to progress when conversion starts
  useEffect(() => {
    if (progress && document.getElementById('progress-section')) {
      document.getElementById('progress-section')?.scrollIntoView({ 
        behavior: 'smooth',
        block: 'center'
      });
    }
  }, [progress]);

  const handleFetchTree = () => {
    if (!onedriveUrl.trim()) {
      toast({
        title: "Error",
        description: "Please enter a OneDrive URL",
        variant: "destructive",
      });
      return;
    }
    fetchFileTree(onedriveUrl);
  };

  const handleConvert = () => {
    startConversion(selectedFiles);
  };

  const handleSignOut = async () => {
    cleanupConversion();
    await clearSession();
    await signOut();
  };

  const isButtonDisabled = isConverting || selectedFiles.size === 0 || !sessionId || isCreatingSession;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Session Info */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                <span className="text-sm font-medium">Session Status</span>
              </div>
              <div className="flex items-center gap-2">
                {isCreatingSession ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span className="text-xs text-muted-foreground">Creating session...</span>
                  </>
                ) : sessionId ? (
                  <>
                    <Badge variant="secondary" className="text-xs">
                      {sessionId.slice(0, 8)}...
                    </Badge>
                    <span className="text-xs text-muted-foreground">Session active</span>
                  </>
                ) : sessionError ? (
                  <>
                    <Badge variant="destructive" className="text-xs">Error</Badge>
                    <span className="text-xs text-muted-foreground">{sessionError}</span>
                  </>
                ) : (
                  <span className="text-xs text-muted-foreground">No session</span>
                )}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={handleSignOut}>
              Sign Out
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* OneDrive URL Input */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5" />
            OneDrive Folder
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="Enter OneDrive folder URL..."
              value={onedriveUrl}
              onChange={(e) => setOnedriveUrl(e.target.value)}
              className="flex-1"
            />
            <Button 
              onClick={handleFetchTree} 
              disabled={isLoadingTree || !onedriveUrl.trim()}
            >
              {isLoadingTree ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Loading...
                </>
              ) : (
                'Load Files'
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* File Tree */}
      {fileTree.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <FileVideo className="h-5 w-5" />
                Files ({totalVobFiles} VOB files found)
              </CardTitle>
              <div className="space-x-2">
                <Button variant="outline" size="sm" onClick={selectAllVobFiles}>
                  Select All VOB
                </Button>
                <Button variant="outline" size="sm" onClick={clearSelection}>
                  Clear Selection
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="max-h-96 overflow-y-auto border rounded-md p-2">
              {fileTree.map((item) => (
                <FileTreeItem
                  key={item.id}
                  item={item}
                  level={0}
                  isSelected={selectedFiles.has(item.id)}
                  isExpanded={expandedFolders.has(item.id)}
                  selectedFiles={selectedFiles}
                  onToggleSelection={toggleFileSelection}
                  onToggleExpansion={toggleFolderExpansion}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Conversion Controls */}
      {selectedFiles.size > 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <span className="text-sm text-muted-foreground">
                  {selectedFiles.size} file{selectedFiles.size !== 1 ? 's' : ''} selected for conversion
                </span>
                {/* Debug info */}
                <div className="text-xs text-muted-foreground">
                  Session: {sessionId ? '✓' : '✗'} | 
                  Converting: {isConverting ? '✓' : '✗'} | 
                  Creating: {isCreatingSession ? '✓' : '✗'} |
                  Error: {sessionError ? '✓' : '✗'}
                </div>
              </div>
              <Button 
                onClick={handleConvert} 
                disabled={isButtonDisabled}
                size="lg"
                className="min-w-[150px]"
              >
                {isConverting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Converting...
                  </>
                ) : isCreatingSession ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Creating Session...
                  </>
                ) : (
                  'Start Conversion'
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progress Display */}
      {progress && (
        <div id="progress-section">
          <ProgressDisplay progress={progress} />
        </div>
      )}
    </div>
  );
};

export default UserProfile;