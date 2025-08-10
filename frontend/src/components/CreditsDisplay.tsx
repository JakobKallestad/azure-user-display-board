import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useCredits } from '@/hooks/useCredits';
import { Coins, Plus, Loader2 } from 'lucide-react';

export const CreditsDisplay: React.FC = () => {
  const { credits, isLoading, addCredits } = useCredits();

  const handleAddCredits = async () => {
    try {
      await addCredits(1.0);
    } catch (error) {
      // Error is already handled in the hook
      console.error('Failed to add credits:', error);
    }
  };

  if (!credits && !isLoading) {
    return null;
  }

  return (
    <Card className="border-2 border-green-200 bg-green-50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-green-800">
            <Coins className="h-5 w-5" />
            Account Credits
          </div>
          <Badge variant="secondary" className="bg-green-200 text-green-800">
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              `$${credits?.credits.toFixed(2) || '0.00'}`
            )}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-muted-foreground">
              Available Balance
            </div>
            <div className="text-2xl font-bold text-green-800">
              ${credits?.credits.toFixed(2) || '0.00'}
            </div>
            <div className="text-xs text-muted-foreground">
              Use credits to process your VOB files
            </div>
          </div>
          <Button
            onClick={handleAddCredits}
            disabled={isLoading}
            variant="outline"
            className="border-green-300 text-green-700 hover:bg-green-100"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Plus className="h-4 w-4 mr-2" />
            )}
            Add $1.00
          </Button>
        </div>
        
        <div className="text-xs text-muted-foreground bg-white p-3 rounded-lg border border-green-200">
          <p className="mb-1">
            <strong>Note:</strong> New users start with $5.00 in credits. 
            Processing costs $1.00 per GB of VOB files.
          </p>
          <p>
            Click "Add $1.00" to add more credits to your account for testing.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}; 