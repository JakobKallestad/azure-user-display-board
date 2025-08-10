import { useState, useCallback, useEffect } from 'react';
import { UserCredits, CreditTransaction } from '@/types';
import { creditsService } from '@/services/credits';
import { useToast } from './use-toast';
import { useAuth } from './useAuth';

export const useCredits = () => {
  const [credits, setCredits] = useState<UserCredits | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const { toast } = useToast();
  const { session } = useAuth();

  const fetchCredits = useCallback(async () => {
    if (!session?.user?.id) return;

    try {
      setIsLoading(true);
      setError(null);
      const userCredits = await creditsService.getUserCredits(session.user.id);
      setCredits(userCredits);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch credits';
      setError(errorMessage);
      console.error('Error fetching credits:', err);
    } finally {
      setIsLoading(false);
    }
  }, [session?.user?.id]);

  const addCredits = useCallback(async (amount: number = 1.0) => {
    if (!session?.user?.id) {
      toast({
        title: "Error",
        description: "No user session found",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsLoading(true);
      const { checkout_url } = await creditsService.createCheckout(session.user.id, amount);
      window.location.href = checkout_url;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to start checkout';
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [session?.user?.id, toast]);

  const deductCredits = useCallback(async (amount: number) => {
    if (!session?.user?.id) {
      throw new Error('No user session found');
    }

    try {
      const transaction = await creditsService.deductCredits(session.user.id, amount);
      
      // Update local state
      setCredits(prev => prev ? {
        ...prev,
        credits: transaction.remaining_credits || prev.credits,
        updated_at: transaction.updated_at
      } : null);

      return transaction;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to deduct credits';
      throw new Error(errorMessage);
    }
  }, [session?.user?.id]);

  const canAfford = useCallback((amount: number): boolean => {
    return credits ? credits.credits >= amount : false;
  }, [credits]);

  // Auto-fetch credits when user session changes
  useEffect(() => {
    if (session?.user?.id) {
      fetchCredits();
    } else {
      setCredits(null);
    }
    // On success redirect, make sure to refresh credits once
    const url = new URL(window.location.href);
    if (url.pathname === '/credits-success') {
      fetchCredits();
    }
  }, [session?.user?.id, fetchCredits]);

  return {
    credits,
    isLoading,
    error,
    fetchCredits,
    addCredits,
    deductCredits,
    canAfford,
  };
}; 