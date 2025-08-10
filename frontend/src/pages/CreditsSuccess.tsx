import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CheckCircle2 } from 'lucide-react';
import { useCredits } from '@/hooks/useCredits';

const CreditsSuccess = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { fetchCredits } = useCredits();

  useEffect(() => {
    // Optionally validate the session_id with backend if desired
    const _sessionId = searchParams.get('session_id');
    // Refresh credits so UI reflects the new balance immediately
    fetchCredits();
  }, [fetchCredits, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            Payment successful
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p>Your credits have been updated. You can now continue converting your files.</p>
          <div className="flex justify-end">
            <Button onClick={() => navigate('/')}>Go to dashboard</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default CreditsSuccess;


