import { useEffect, useState } from 'react';
import { createClient, Session } from '@supabase/supabase-js';
import { useToast } from './use-toast';

// You'll need to add these to your environment variables
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

const supabase = createClient(supabaseUrl, supabaseAnonKey);

export const useAuth = () => {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const refreshAccessToken = async (): Promise<void> => {
    try {
      const { data, error } = await supabase.auth.refreshSession();
      if (error) throw error;
      toast({
        title: "Success",
        description: "Token refreshed successfully",
      });
    } catch (error) {
      console.error('Error refreshing token:', error);
      toast({
        title: "Error",
        description: "Failed to refresh token",
        variant: "destructive",
      });
      throw error;
    }
  };

  const signOut = async (): Promise<void> => {
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      toast({
        title: "Success",
        description: "Signed out successfully",
      });
    } catch (error) {
      console.error('Error signing out:', error);
      toast({
        title: "Error",
        description: "Failed to sign out",
        variant: "destructive",
      });
      throw error;
    }
  };

  return {
    session,
    loading,
    refreshAccessToken,
    signOut,
    isAuthenticated: !!session,
    providerToken: session?.provider_token,
    refreshToken: session?.provider_refresh_token,
    supabaseRefreshToken: session?.refresh_token,
    supabase, // Export supabase client for other uses
  };
}; 