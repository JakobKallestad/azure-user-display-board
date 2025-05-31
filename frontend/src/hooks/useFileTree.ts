import { useState, useCallback } from 'react';
import { FileItem, FileTreeResponse } from '@/types';
import { apiService } from '@/services/api';
import { useToast } from './use-toast';
import { useAuth } from './useAuth';
import { extractItemIdFromUrl, isValidOneDriveUrl } from '@/utils/url';
import { processFileTree } from '@/utils/fileTree';

export const useFileTree = () => {
  const [fileTree, setFileTree] = useState<FileItem[]>([]);
  const [totalVobFiles, setTotalVobFiles] = useState(0);
  const [isLoadingTree, setIsLoadingTree] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  const { toast } = useToast();
  const { providerToken, refreshAccessToken } = useAuth();

  const fetchFileTree = useCallback(async (onedriveUrl: string) => {
    if (!isValidOneDriveUrl(onedriveUrl)) {
      toast({
        title: "Error",
        description: "Please enter a valid OneDrive URL with an item ID",
        variant: "destructive",
      });
      return;
    }

    const itemId = extractItemIdFromUrl(onedriveUrl);
    if (!itemId) {
      toast({
        title: "Error",
        description: "Could not extract item ID from URL",
        variant: "destructive",
      });
      return;
    }

    if (!providerToken) {
      toast({
        title: "Error",
        description: "No provider token available",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsLoadingTree(true);
      
      const data = await apiService.fetchFileTree(itemId, providerToken);
      setFileTree(data.tree);
      setTotalVobFiles(data.total_vob_files);

      // Auto-select all VOB files and expand folders containing them
      const { selectedVobFiles, foldersToExpand } = processFileTree(data.tree);
      setSelectedFiles(selectedVobFiles);
      setExpandedFolders(foldersToExpand);

      toast({
        title: "Success",
        description: `Found ${data.total_vob_files} VOB files`,
      });
    } catch (error) {
      if (error instanceof Error && 'status' in error && error.status === 401) {
        try {
          await refreshAccessToken();
          // Retry with new token
          await fetchFileTree(onedriveUrl);
        } catch (refreshError) {
          toast({
            title: "Error",
            description: "Failed to refresh authentication",
            variant: "destructive",
          });
        }
      } else {
        console.error('Error fetching file tree:', error);
        toast({
          title: "Error",
          description: error instanceof Error ? error.message : 'Failed to fetch file tree',
          variant: "destructive",
        });
      }
    } finally {
      setIsLoadingTree(false);
    }
  }, [providerToken, refreshAccessToken, toast]);

  const toggleFileSelection = useCallback((fileId: string) => {
    setSelectedFiles(prev => {
      const newSet = new Set(prev);
      if (newSet.has(fileId)) {
        newSet.delete(fileId);
      } else {
        newSet.add(fileId);
      }
      return newSet;
    });
  }, []);

  const toggleFolderExpansion = useCallback((folderId: string) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(folderId)) {
        newSet.delete(folderId);
      } else {
        newSet.add(folderId);
      }
      return newSet;
    });
  }, []);

  // Helper function to check if an item (or any of its children) is selected
  const isItemOrChildSelected = useCallback((item: FileItem, selectedFiles: Set<string>): boolean => {
    if (selectedFiles.has(item.id)) {
      return true;
    }
    if (item.children) {
      return item.children.some(child => isItemOrChildSelected(child, selectedFiles));
    }
    return false;
  }, []);

  const selectAllVobFiles = useCallback(() => {
    const { selectedVobFiles } = processFileTree(fileTree);
    setSelectedFiles(selectedVobFiles);
  }, [fileTree]);

  const clearSelection = useCallback(() => {
    setSelectedFiles(new Set());
  }, []);

  return {
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
  };
}; 