// @ts-nocheck

import { redirect } from 'next/navigation';
import AdminAnalyticsDashboard from '../../components/admin-analytics-dashboard';
import { getSession } from '../../lib/auth/session';
import { loadAdminAnalytics } from '../../lib/admin-analytics';

export const dynamic = 'force-dynamic';

export default async function AdminPage() {
  const session = await getSession();
  if (!session) redirect('/login');
  if (session.reviewerId !== 'admin') redirect('/');

  try {
    const analytics = await loadAdminAnalytics();
    return <AdminAnalyticsDashboard analytics={analytics} />;
  } catch (error) {
    return (
      <main className="errorPage">
        <div className="errorPageCard">
          <h1>Admin analytics failed to load</h1>
          <p>{error instanceof Error ? error.message : String(error)}</p>
        </div>
      </main>
    );
  }
}
