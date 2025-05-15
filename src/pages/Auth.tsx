import { useState, useEffect } from 'react';
import { supabase } from "@/integrations/supabase/client";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/sonner";
import { useAuth } from '@/context/AuthContext';

const Auth = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    // If user is already authenticated, redirect to home page
    if (user) {
      navigate('/');
      return;
    }

    // Check if there's a hash in the URL (authentication callback)
    const handleAuthRedirect = async () => {
      const hash = window.location.hash;
      if (hash && hash.includes('access_token')) {
        setLoading(true);
        try {
          // Parse the URL hash to extract token
          const params = new URLSearchParams(hash.substring(1));
          const accessToken = params.get('access_token');
          
          if (!accessToken) {
            throw new Error('No access token found in URL');
          }
          
          console.log('Found access token, setting session');
          
          // Set the session with the access token
          const { data, error } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: '',
          });
          
          if (error) {
            console.error('Error setting session:', error);
            toast.error('Authentication failed: ' + error.message);
          } else {
            console.log('Auth succeeded, redirecting to home page');
            toast.success('Successfully signed in');
            
            // Use a slight delay to ensure the auth state is updated before redirect
            setTimeout(() => {
              // Hard redirect to clear URL hash
              window.location.href = '/';
            }, 500);
          }
        } catch (error: any) {
          console.error('Error processing authentication:', error);
          toast.error('Authentication failed: ' + (error.message || 'Unknown error'));
        } finally {
          setLoading(false);
        }
      }
    };

    handleAuthRedirect();
  }, [user, navigate]);

  const handleAzureSignIn = async () => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'azure',
        options: {
          scopes: 'openid email profile offline_access https://graph.microsoft.com/.default',
          redirectTo: window.location.origin + '/auth'
        }
      });

      if (error) {
        throw error;
      }
    } catch (error: any) {
      console.error('Error signing in:', error);
      toast.error('Failed to sign in with Azure AD: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold">Welcome to 1Driver</CardTitle>
          <CardDescription>
            Sign in with your Microsoft account to continue
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4">
          <Button 
            onClick={handleAzureSignIn} 
            className="w-full" 
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign in with Microsoft'}
          </Button>
        </CardContent>
        <CardFooter className="text-xs text-center text-slate-500">
          <p className="w-full">Your information will be fetched from Microsoft Graph API</p>
        </CardFooter>
      </Card>
    </div>
  );
};

export default Auth;
