import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useCredits } from '@/hooks/useCredits';
import { Coins, Plus, Loader2 } from 'lucide-react';

export const CreditsDisplay: React.FC = () => {
  const { credits, isLoading, addCredits } = useCredits();
  const [customAmount, setCustomAmount] = React.useState('');
  const [customLoading, setCustomLoading] = React.useState(false);

  const handleAddCredits = async (amount: number) => {
    try {
      await addCredits(amount);
    } catch (error) {
      // Error is already handled in the hook
      console.error('Failed to add credits:', error);
    }
  };

  const handleCustomTopUp = async () => {
    const amount = parseFloat(customAmount);
    if (isNaN(amount) || amount <= 0) return;
    setCustomLoading(true);
    try {
      await addCredits(amount);
    } catch (error) {
      // Error is already handled
    } finally {
      setCustomLoading(false);
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
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <div className="text-sm text-muted-foreground">Available Balance</div>
            <div className="text-2xl font-bold text-green-800">
              ${credits?.credits.toFixed(2) || '0.00'}
            </div>
            <div className="text-xs text-muted-foreground">Use credits to process your VOB files</div>
          </div>
          <div className="flex flex-col gap-2 sm:gap-1 sm:flex-row">
            {[1, 2, 5, 10].map((amt) => (
              <Button
                key={amt}
                onClick={() => handleAddCredits(amt)}
                disabled={isLoading}
                variant="outline"
                className="border-green-300 text-green-700 hover:bg-green-100 min-w-[90px]"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Add ${amt}.00
              </Button>
            ))}
            <div className="flex items-center gap-1">
              <input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="Custom"
                value={customAmount}
                onChange={e => setCustomAmount(e.target.value)}
                className="w-20 px-2 py-1 border rounded text-sm"
              />
              <Button
                onClick={handleCustomTopUp}
                disabled={customLoading || isLoading || !customAmount || parseFloat(customAmount) <= 0}
                variant="outline"
                className="border-green-300 text-green-700 hover:bg-green-100"
              >
                {customLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Add
              </Button>
            </div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground bg-white p-3 rounded-lg border border-green-200">
          <p className="mb-1">
            <strong>Note:</strong> New users start with $5.00 in credits. 
            Processing costs $1.00 per GB of VOB files.
          </p>
          <p>
            Use the buttons above to add more credits to your account for testing.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}; 