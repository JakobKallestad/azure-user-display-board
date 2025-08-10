import { UserCredits, CreditTransaction } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const creditsService = {
  async getUserCredits(userId: string): Promise<UserCredits> {
    const response = await fetch(`${API_BASE_URL}/credits/${userId}`);
    if (!response.ok) {
      throw new Error('Failed to fetch user credits');
    }
    return response.json();
  },

  async createCheckout(userId: string, amount: number = 1.0): Promise<{ checkout_url: string }> {
    const response = await fetch(`${API_BASE_URL}/payments/create-checkout-session?user_id=${encodeURIComponent(userId)}&amount=${amount}`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to create checkout session');
    }
    return response.json();
  },

  async addCredits(userId: string, amount: number = 1.0): Promise<CreditTransaction> {
    const response = await fetch(`${API_BASE_URL}/credits/${userId}/add?amount=${amount}`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to add credits');
    }
    return response.json();
  },

  async deductCredits(userId: string, amount: number): Promise<CreditTransaction> {
    const response = await fetch(`${API_BASE_URL}/credits/${userId}/deduct?amount=${amount}`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to deduct credits');
    }
    return response.json();
  },
}; 