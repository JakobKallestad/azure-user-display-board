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
import { ProcessingEstimates } from './ProcessingEstimates';
import { formatFileSize } from '@/utils/fileTree';
import { useCredits } from '@/hooks/useCredits';
import { CreditsDisplay } from './CreditsDisplay';
import { ConversionConfirmDialog } from './ConversionConfirmDialog';

const UserProfile: React.FC = () => {
  const [onedriveUrl, setOnedriveUrl] = useState('');
  
  const { session, signOut, loading } = useAuth();
  const { toast } = useToast();
  const { sessionId, isCreatingSession, sessionError, clearSession } = useSession();
  
  const {
    fileTree,
    totalVobFiles,
    totalVobSize,
    estimates,
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

  // Add credits hook
  const { credits, canAfford, deductCredits, fetchCredits } = useCredits();

  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isStartingConversion, setIsStartingConversion] = useState(false);

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

  const handleStartConversion = async () => {
    console.log('🚀 Starting conversion process...');
    console.log('Session:', { 
      sessionId, 
      hasRefreshToken: !!session?.refresh_token, 
      hasProviderRefreshToken: !!session?.provider_refresh_token,
      userId: session?.user?.id,
      refreshTokenLength: session?.refresh_token?.length,
      providerRefreshTokenLength: session?.provider_refresh_token?.length,
      refreshTokenStart: session?.refresh_token?.substring(0, 20) + '...',
      providerRefreshTokenStart: session?.provider_refresh_token?.substring(0, 20) + '...'
      
    });
    console.log('Selected files:', Array.from(selectedFiles));
    console.log('Estimates:', estimates);
    
    if (!sessionId) {
      toast({
        title: "Error",
        description: "No session available",
        variant: "destructive",
      });
      return;
    }

    if (!session?.provider_refresh_token) {
      toast({
        title: "Error", 
        description: "No provider refresh token available",
        variant: "destructive",
      });
      return;
    }

    // Check if user can afford the conversion - use the correct field name
    const estimatedCost = estimates?.estimated_cost || 0;
    console.log('💰 Credit check:', { 
      estimatedCost, 
      currentCredits: credits?.credits, 
      canAfford: canAfford(estimatedCost),
      estimatesObject: estimates 
    });
    
    if (!canAfford(estimatedCost)) {
      toast({
        title: "Insufficient Credits",
        description: `You need $${estimatedCost.toFixed(2)} but only have $${credits?.credits.toFixed(2) || '0.00'}`,
        variant: "destructive",
      });
      return;
    }

    // Show the prettier confirmation dialog
    setShowConfirmDialog(true);
  };

  const handleConfirmConversion = async () => {
    setIsStartingConversion(true);
    
    try {
      const selectedFileIds = Array.from(selectedFiles);
      const estimatedCost = estimates?.estimated_cost || 0;
      const conversionData = {
        file_ids: selectedFileIds,
        refresh_token: session!.provider_refresh_token,
        user_id: session!.user.id,
        estimated_cost: estimatedCost,
      };
      
      console.log('📤 Sending conversion request:', {
        file_ids: conversionData.file_ids,
        refresh_token_length: conversionData.refresh_token.length,
        refresh_token_starts_with: conversionData.refresh_token.substring(0, 10),
        estimated_cost: conversionData.estimated_cost,
        user_id: conversionData.user_id
      });
      
      await startConversion(conversionData);

      // Immediately update credits UI to reflect the deduction
      await fetchCredits();
      
      setShowConfirmDialog(false);
      toast({
        title: "Conversion Started",
        description: `Processing ${selectedFiles.size} files. Credits have been deducted.`,
      });
    } catch (error) {
      console.error('❌ Conversion failed:', error);
      // If conversion fails to start, refresh credits to show any refunds
      await fetchCredits();
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to start conversion",
        variant: "destructive",
      });
    } finally {
      setIsStartingConversion(false);
    }
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
                Files ({totalVobFiles} VOB files found - {formatFileSize(totalVobSize)})
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

      {/* Add Credits Display after user info */}
      <CreditsDisplay />

      {/* Processing Estimates */}
      {estimates && selectedFiles.size > 0 && (
        <ProcessingEstimates 
          estimates={estimates}
          selectedFilesCount={selectedFiles.size}
          totalFilesCount={totalVobFiles}
          userCredits={credits?.credits || 0}
        />
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
                onClick={handleStartConversion} 
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

      <ConversionConfirmDialog
        isOpen={showConfirmDialog}
        onClose={() => setShowConfirmDialog(false)}
        onConfirm={handleConfirmConversion}
        fileCount={selectedFiles.size}
        estimatedCost={estimates?.estimated_cost || 0}
        currentBalance={credits?.credits || 0}
        remainingBalance={(credits?.credits || 0) - (estimates?.estimated_cost || 0)}
        isLoading={isStartingConversion}
      />
    </div>
  );
};

export default UserProfile;