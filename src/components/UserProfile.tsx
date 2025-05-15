
import { useState, useEffect } from 'react';
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

interface UserData {
  displayName: string;
  givenName: string;
  surname: string;
  mail: string;
  jobTitle: string;
  officeLocation: string;
  mobilePhone: string;
  businessPhones: string[];
  userPrincipalName: string;
  preferredLanguage: string;
  id: string;
}

const UserProfile = () => {
  const [userData, setUserData] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUserData();
  }, []);

  const fetchUserData = async () => {
    try {
      setLoading(true);
      
      // Get the session which contains the Microsoft access token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session) {
        throw new Error('No active session');
      }

      // The provider token from Azure AD
      const providerToken = session.provider_token;
      
      if (!providerToken) {
        throw new Error('No provider token available');
      }

      // Make request to Microsoft Graph API
      const response = await fetch('https://graph.microsoft.com/v1.0/me', {
        headers: {
          'Authorization': `Bearer ${providerToken}`
        }
      });

      if (!response.ok) {
        throw new Error(`Graph API returned ${response.status}`);
      }

      const data = await response.json();
      setUserData(data);
    } catch (error: any) {
      console.error('Error fetching user data:', error);
      toast.error(error.message || 'Failed to load your profile');
    } finally {
      setLoading(false);
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
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-center">
          <p>Loading your profile...</p>
        </div>
      </div>
    );
  }

  if (!userData) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-center">
          <p>Could not load profile information</p>
          <Button onClick={fetchUserData} className="mt-4">Try Again</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center justify-between">
            <span>User Profile</span>
            <Button variant="outline" onClick={handleSignOut}>Sign Out</Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="text-xl font-bold">{userData.displayName}</div>
              <div className="text-muted-foreground">{userData.jobTitle}</div>
            </div>
            <div className="space-y-2">
              <div className="font-medium">Email</div>
              <div className="text-muted-foreground">{userData.mail}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
            <InfoItem label="First Name" value={userData.givenName} />
            <InfoItem label="Last Name" value={userData.surname} />
            <InfoItem label="Office Location" value={userData.officeLocation} />
            <InfoItem label="Mobile Phone" value={userData.mobilePhone} />
            <InfoItem label="Business Phone" value={userData.businessPhones?.[0]} />
            <InfoItem label="Username" value={userData.userPrincipalName} />
            <InfoItem label="Preferred Language" value={userData.preferredLanguage} />
            <InfoItem label="User ID" value={userData.id} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

const InfoItem = ({ label, value }: { label: string; value?: string }) => (
  <div className="space-y-1">
    <div className="text-sm font-medium">{label}</div>
    <div className="text-sm text-muted-foreground">{value || "Not provided"}</div>
  </div>
);

export default UserProfile;
