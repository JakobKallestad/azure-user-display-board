import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { FileVideo, DollarSign, Wallet, Calculator } from 'lucide-react';

interface ConversionConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  fileCount: number;
  estimatedCost: number;
  currentBalance: number;
  remainingBalance: number;
  isLoading?: boolean;
}

export const ConversionConfirmDialog: React.FC<ConversionConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  fileCount,
  estimatedCost,
  currentBalance,
  remainingBalance,
  isLoading = false,
}) => {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileVideo className="h-5 w-5 text-blue-600" />
            Confirm Conversion
          </DialogTitle>
          <DialogDescription>
            Review the details before starting your file conversion.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* File Count */}
          <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
            <div className="flex items-center gap-2">
              <FileVideo className="h-4 w-4 text-blue-600" />
              <span className="text-sm font-medium">Files to convert</span>
            </div>
            <Badge variant="secondary">{fileCount} VOB files</Badge>
          </div>

          <Separator />

          {/* Cost Breakdown */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Calculator className="h-4 w-4 text-orange-600" />
                <span className="text-sm font-medium">Estimated cost</span>
              </div>
              <span className="text-lg font-semibold text-orange-600">
                ${estimatedCost.toFixed(2)}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wallet className="h-4 w-4 text-green-600" />
                <span className="text-sm font-medium">Current balance</span>
              </div>
              <span className="text-sm font-medium">
                ${currentBalance.toFixed(2)}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-gray-600" />
                <span className="text-sm font-medium">Remaining after</span>
              </div>
              <span className={`text-sm font-medium ${remainingBalance >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                ${remainingBalance.toFixed(2)}
              </span>
            </div>
          </div>

          <Separator />

          {/* Important Notice */}
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <p className="text-xs text-amber-800">
              <strong>Important:</strong> Credits will be deducted when conversion starts. 
              If processing fails, you will receive a full refund automatically.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button 
            onClick={onConfirm} 
            disabled={isLoading || remainingBalance < 0}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {isLoading ? 'Starting...' : 'Start Conversion'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}; 