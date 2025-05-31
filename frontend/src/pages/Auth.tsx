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
    if (user) {
      navigate('/'); // Redirect to home page if user is authenticated
    }
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
    } catch (error) {
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
