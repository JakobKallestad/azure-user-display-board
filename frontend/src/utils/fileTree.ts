import { FileItem } from '@/types';

export const processFileTree = (tree: FileItem[]): {
  selectedVobFiles: Set<string>;
  foldersToExpand: Set<string>;
} => {
  const selectedVobFiles = new Set<string>();
  const foldersToExpand = new Set<string>();

  const processNode = (node: FileItem, parentPath = ''): boolean => {
    let hasVobFiles = false;

    if (node.type === 'file' && node.is_vob) {
      selectedVobFiles.add(node.id);
      hasVobFiles = true;
    } else if (node.type === 'folder' && node.children) {
      for (const child of node.children) {
        if (processNode(child, node.path)) {
          hasVobFiles = true;
        }
      }
      if (hasVobFiles) {
        foldersToExpand.add(node.id);
      }
    }

    return hasVobFiles;
  };

  tree.forEach(node => processNode(node));
  return { selectedVobFiles, foldersToExpand };
};

export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// Add new utility functions
export const formatDuration = (minutes: number): string => {
  if (minutes < 60) {
    return `${Math.round(minutes)} minutes`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = Math.round(minutes % 60);
  if (remainingMinutes === 0) {
    return `${hours} hour${hours !== 1 ? 's' : ''}`;
  }
  return `${hours}h ${remainingMinutes}m`;
};

export const formatCost = (cost: number): string => {
  return `$${cost.toFixed(2)}`;
}; 