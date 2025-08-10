import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ProcessingEstimates as EstimatesType } from '@/types';
import { formatFileSize, formatDuration, formatCost } from '@/utils/fileTree';
import { Clock, DollarSign, HardDrive, Calculator } from 'lucide-react';

interface ProcessingEstimatesProps {
  estimates: EstimatesType;
  selectedFilesCount: number;
  totalFilesCount: number;
  userCredits?: number;
}

export const ProcessingEstimates: React.FC<ProcessingEstimatesProps> = ({
  estimates,
  selectedFilesCount,
  totalFilesCount,
  userCredits = 0
}) => {
  // Calculate estimates for selected files only
  const selectionRatio = totalFilesCount > 0 ? selectedFilesCount / totalFilesCount : 0;
  const selectedSize = estimates.total_size_gb * selectionRatio;
  const selectedTime = estimates.estimated_minutes * selectionRatio;
  const selectedCost = estimates.estimated_cost * selectionRatio;
  
  // Check if user can afford the processing
  const canAfford = userCredits >= selectedCost;
  const shortfall = selectedCost - userCredits;

  return (
    <Card className="border-2 border-blue-200 bg-blue-50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-blue-800">
          <Calculator className="h-5 w-5" />
          Processing Estimates
          <Badge variant="secondary" className="bg-blue-200 text-blue-800">
            {selectedFilesCount} of {totalFilesCount} files selected
          </Badge>
          {!canAfford && selectedCost > 0 && (
            <Badge variant="destructive" className="ml-2">
              Insufficient Credits
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* File Size */}
          <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-blue-200">
            <div className="p-2 bg-blue-100 rounded-lg">
              <HardDrive className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Total Size</div>
              <div className="font-semibold text-blue-800">
                {formatFileSize(selectedSize * 1024 ** 3)}
              </div>
              <div className="text-xs text-muted-foreground">
                {selectedSize.toFixed(2)} GB
              </div>
            </div>
          </div>

          {/* Processing Time */}
          <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-orange-200">
            <div className="p-2 bg-orange-100 rounded-lg">
              <Clock className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Est. Time</div>
              <div className="font-semibold text-orange-800">
                {formatDuration(selectedTime)}
              </div>
              <div className="text-xs text-muted-foreground">
                Based on 300MB = 45min
              </div>
            </div>
          </div>

          {/* Cost */}
          <div className={`flex items-center gap-3 p-3 bg-white rounded-lg border ${
            canAfford ? 'border-green-200' : 'border-red-200'
          }`}>
            <div className={`p-2 rounded-lg ${
              canAfford ? 'bg-green-100' : 'bg-red-100'
            }`}>
              <DollarSign className={`h-5 w-5 ${
                canAfford ? 'text-green-600' : 'text-red-600'
              }`} />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Est. Cost</div>
              <div className={`font-semibold ${
                canAfford ? 'text-green-800' : 'text-red-800'
              }`}>
                {formatCost(selectedCost)}
              </div>
              <div className="text-xs text-muted-foreground">
                $1.00 per GB
              </div>
              {!canAfford && selectedCost > 0 && (
                <div className="text-xs text-red-600 font-medium">
                  Need ${shortfall.toFixed(2)} more
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Additional Info */}
        <div className="text-xs text-muted-foreground bg-white p-3 rounded-lg border border-blue-200">
          <p className="mb-1">
            <strong>Note:</strong> These are estimates based on average processing times and may vary depending on file complexity and system load.
          </p>
          <p>
            Processing includes downloading, converting to MP4, and uploading back to OneDrive.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}; 