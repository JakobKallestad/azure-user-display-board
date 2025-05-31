import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import UserProfile from '@/components/UserProfile';

const Index = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !user) {
      console.log('No user found, redirecting to auth page');
      navigate('/auth');
    } else if (user) {
      console.log('User found, displaying dashboard');
    }
  }, [user, loading, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100">
        <div className="text-center">
          <p className="text-xl">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-4 md:p-8">
      <div className="max-w-8xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">1Driver Dashboard</h1>
        {user ? (
          <UserProfile />
        ) : (
          <div className="text-center py-10">
            <p>Please sign in to view your profile</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Index;
