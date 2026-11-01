import { lazy, Suspense, useEffect } from 'react';
import { Loading, ToastProvider } from './components/Common';
import { useI18n } from './i18n';
import { match, useLocation } from './lib/router';
import { Landing } from './pages/Landing';
import { LinkOpenPage, TryPage } from './pages/LinkOpen';
import { CreditsPage, NotFoundPage, RulesPage } from './pages/Public';
import { StartPage } from './pages/Start';
import { Tour } from './components/Tour';

const HouseholdApp = lazy(() => import('./pages/HouseholdApp').then((m) => ({ default: m.HouseholdApp })));

export function App() {
  const { path } = useLocation();
  const { d } = useI18n();

  useEffect(() => {
    if (path === '/' || path === '/rules' || path === '/credits' || path === '/try' || path === '/start') {
      const names: Record<string, string> = { '/rules': d.rules.title, '/credits': d.credits.title, '/try': d.landing.heroCta, '/start': d.start.title };
      document.title = names[path] ? `${names[path]} | If I Disappear` : `If I Disappear: ${d.app.tagline}`;
    }
  }, [path, d]);

  let page;
  const household = match('/h/:id', path) || (path.startsWith('/h/') ? { id: path.split('/')[2] } : null);
  const link = match('/l/:token', path);
  if (path === '/') page = <Landing />;
  else if (path === '/try') page = <TryPage />;
  else if (path === '/start') page = <StartPage />;
  else if (path === '/rules') page = <RulesPage />;
  else if (path === '/credits') page = <CreditsPage />;
  else if (link) page = <LinkOpenPage token={link.token} />;
  else if (household?.id) page = <HouseholdApp id={household.id} path={path} />;
  else page = <NotFoundPage />;

  return (
    <ToastProvider>
      <Suspense fallback={<Loading />}>{page}</Suspense>
      <Tour />
    </ToastProvider>
  );
}
