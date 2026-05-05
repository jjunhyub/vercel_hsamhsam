// @ts-nocheck

import { redirect } from 'next/navigation';
import AdminAnalyticsDashboard from '../../components/admin-analytics-dashboard';
import LocalizedErrorCard from '../../components/localized-error-card';
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
        <LocalizedErrorCard
          titleKey="error.adminLoadTitle"
          message={error instanceof Error ? error.message : String(error)}
        />
      </main>
    );
  }
}
