import React from 'react';
import { ChevronRight, ChevronDown, File, Folder, Video } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { FileItem } from '@/types';
import { formatFileSize } from '@/utils/fileTree';
import { cn } from '@/lib/utils';

interface FileTreeItemProps {
  item: FileItem;
  level: number;
  isSelected: boolean;
  isExpanded: boolean;
  selectedFiles: Set<string>;
  onToggleSelection: (fileId: string) => void;
  onToggleExpansion: (folderId: string) => void;
}

export const FileTreeItem: React.FC<FileTreeItemProps> = ({
  item,
  level,
  isSelected,
  isExpanded,
  selectedFiles,
  onToggleSelection,
  onToggleExpansion,
}) => {
  const isFolder = item.type === 'folder';
  const hasChildren = isFolder && item.children.length > 0;

  // Helper function to check if this item or any child is selected
  const isItemOrChildSelected = (item: FileItem): boolean => {
    if (selectedFiles.has(item.id)) {
      return true;
    }
    if (item.children) {
      return item.children.some(child => isItemOrChildSelected(child));
    }
    return false;
  };

  const itemSelected = isItemOrChildSelected(item);

  return (
    <div className="select-none">
      <div
        className={cn(
          "flex items-center py-1 px-2 hover:bg-accent rounded-sm cursor-pointer",
          level > 0 && "ml-4"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {/* Expansion toggle for folders */}
        {hasChildren && (
          <button
            onClick={() => onToggleExpansion(item.id)}
            className="mr-1 p-1 hover:bg-accent rounded"
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        )}

        {/* Checkbox for VOB files */}
        {item.is_vob && (
          <Checkbox
            checked={selectedFiles.has(item.id)}
            onCheckedChange={() => onToggleSelection(item.id)}
            className="mr-2"
          />
        )}

        {/* Icon */}
        <div className="mr-2">
          {isFolder ? (
            <Folder className={cn(
              "h-4 w-4",
              itemSelected ? "text-blue-600" : "text-blue-500"
            )} />
          ) : item.is_vob ? (
            <Video className="h-4 w-4 text-green-500" />
          ) : (
            <File className="h-4 w-4 text-gray-500" />
          )}
        </div>

        {/* File/folder name and info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <span className={cn(
              "truncate",
              item.is_vob && selectedFiles.has(item.id) && "font-medium text-green-700",
              item.is_vob && !selectedFiles.has(item.id) && "text-green-600",
              isFolder && itemSelected && "font-medium text-blue-700"
            )}>
              {item.name}
            </span>
            <div className="flex items-center space-x-2 text-xs text-muted-foreground">
              {isFolder && item.vob_count > 0 && (
                <span className={cn(
                  "px-2 py-1 rounded",
                  itemSelected 
                    ? "bg-green-200 text-green-900 font-medium" 
                    : "bg-green-100 text-green-800"
                )}>
                  {item.vob_count} VOB{item.vob_count !== 1 ? 's' : ''}
                </span>
              )}
              <span>{formatFileSize(item.size)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Render children if expanded */}
      {hasChildren && isExpanded && (
        <div>
          {item.children.map((child) => (
            <FileTreeItem
              key={child.id}
              item={child}
              level={level + 1}
              isSelected={selectedFiles.has(child.id)}
              isExpanded={isExpanded}
              selectedFiles={selectedFiles}
              onToggleSelection={onToggleSelection}
              onToggleExpansion={onToggleExpansion}
            />
          ))}
        </div>
      )}
    </div>
  );
}; 