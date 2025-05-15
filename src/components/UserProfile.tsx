import { useState, useEffect } from 'react';
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

const UserProfile = () => {
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [children, setChildren] = useState([]);

  useEffect(() => {
    fetchUserData();
  }, []);

  const fetchUserData = async () => {
    try {
      setLoading(true);
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) throw new Error('No active session');
      const providerToken = session.provider_token;
      if (!providerToken) throw new Error('No provider token available');

      const response = await fetch('https://graph.microsoft.com/v1.0/me', {
        headers: { 'Authorization': `Bearer ${providerToken}` }
      });

      if (!response.ok) throw new Error(`Graph API returned ${response.status}`);
      const data = await response.json();
      setUserData(data);
    } catch (error) {
      console.error('Error fetching user data:', error);
      toast.error(error.message || 'Failed to load your profile');
    } finally {
      setLoading(false);
    }
  };

  const fetchChildren = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const providerToken = session?.provider_token;
      if (!providerToken) throw new Error('No provider token available');

      const response = await fetch(`http://localhost:8000/items/47575C443A523D3A!76020/children?token=${providerToken}`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${providerToken}` }
      });

      if (!response.ok) throw new Error(`Error: ${response.statusText}`);
      const result = await response.json();
      setChildren(result.value); // Assuming the response has a 'value' field
    } catch (error) {
      console.error('Error fetching children:', error);
      toast.error('Failed to fetch children');
    }
  };

  const handleConvertFiles = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const providerToken = session?.provider_token;
      if (!providerToken) throw new Error('No provider token available');

      const response = await fetch('http://localhost:7000/convert', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${providerToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: providerToken }),
      });

      if (!response.ok) throw new Error(`Error: ${response.statusText}`);
      const result = await response.json();
      toast.success(result.message);
    } catch (error) {
      console.error('Error converting files:', error);
      toast.error('Failed to convert files');
    }
  };

  const handleSignOut = async () => {
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      toast.success('Signed out successfully');
    } catch (error) {
      console.error('Error signing out:', error);
      toast.error('Failed to sign out');
    }
  };

  if (loading) {
    return <div>Loading your profile...</div>;
  }

  return (
    <div>
      <Card>
        <CardHeader>
          <CardTitle>User Profile</CardTitle>
          <Button onClick={handleSignOut}>Sign Out</Button>
        </CardHeader>
        <CardContent>
          <div>{userData?.displayName}</div>
          <Button onClick={fetchChildren}>Fetch Children</Button>
          <Button onClick={handleConvertFiles}>Convert Files</Button>
          <div>
            {children.map(child => (
              <div key={child.id}>{child.name}</div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default UserProfile;