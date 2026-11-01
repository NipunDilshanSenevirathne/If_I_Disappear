import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorState, Loading } from '../components/Common';
import { Logo } from '../components/Logo';
import { BottomNav, HouseholdContext, TopBar, type HouseholdCtx } from '../components/Shell';
import { pick, useI18n } from '../i18n';
import { Api, ApiError, forgetHousehold, getToken } from '../lib/api';
import { forgetOffline } from '../lib/offline';
import { useOnline } from '../lib/hooks';
import { Link, match } from '../lib/router';
import type { Board } from '../lib/types';
import { BoardPage } from './Board';
import { CardPage } from './Card';
import { EvidencePage } from './Evidence';
import { HelpPage } from './Help';
import { PeoplePage } from './People';
import { ProvePage } from './Prove';
import { RecordPage } from './Record';
import { ReviewPage } from './Review';
import { TaskPage } from './Task';

function NoAccess({ gone = false }: { gone?: boolean }) {
  const { d } = useI18n();
  return (
    <div className="center-page">
      <Logo />
      <p className="state">{gone ? d.link.turnedOff : d.link.noAccess}</p>
      <Link to="/try" className="btn btn-primary">
        {d.landing.heroCta}
      </Link>
      <Link to="/" className="btn btn-quiet">
        {d.link.home}
      </Link>
    </div>
  );
}

export function HouseholdApp({ id, path }: { id: string; path: string }) {
  const { d, lang } = useI18n();
  const online = useOnline();
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [minutes, setMinutes] = useState(20);
  const token = getToken(id);

  const refresh = useCallback(async () => {
    try {
      const b = await Api.board(id, minutes);
      setBoard(b);
      setError(null);
    } catch (e) {
      setError(e as Error);
    }
  }, [id, minutes]);

  useEffect(() => {
    if (token) void refresh();
  }, [token, refresh]);

  // The server says this link is over (replaced, turned off, or the home deleted): what this
  // phone saved for it goes too. Never on a lost connection, only on the server's answer.
  const gone = error instanceof ApiError && (error.status === 401 || error.status === 404);
  useEffect(() => {
    if (!gone) return;
    void forgetOffline(id);
    forgetHousehold(id);
  }, [gone, id]);

  const ctx = useMemo<HouseholdCtx | null>(() => (board ? { id, board, refresh, minutes, setMinutes } : null), [id, board, refresh, minutes]);

  const rest = path.slice(`/h/${id}`.length) || '/';
  const taskMatch = match('/task/:key', rest);
  const page = taskMatch ? 'task' : rest.split('/')[1] || 'home';

  useEffect(() => {
    const titles: Record<string, string> = { home: d.nav.home, record: d.nav.record, prove: d.nav.prove, help: d.nav.help, card: d.nav.card, review: d.nav.review, evidence: d.nav.evidence, people: d.nav.people };
    const task = taskMatch && board ? board.tasks.find((t) => t.key === taskMatch.key) : null;
    const name = task ? pick(task, 'title', lang) : titles[page] || '';
    document.title = `${name ? `${name} | ` : ''}If I Disappear`;
  }, [page, board, lang, d, taskMatch]);

  if (gone) return <NoAccess gone />;
  if (!token) return <NoAccess />;
  if (error && !board) {
    return (
      <div className="center-page">
        <Logo />
        <ErrorState error={error} onRetry={refresh} />
      </div>
    );
  }
  if (!ctx) return <Loading />;

  const back = page === 'task' || page === 'review' || page === 'evidence' || page === 'people' ? `/h/${id}` : undefined;
  let content;
  switch (page) {
    case 'task':
      content = <TaskPage taskKey={taskMatch!.key} />;
      break;
    case 'review':
      content = <ReviewPage />;
      break;
    case 'record':
      content = <RecordPage />;
      break;
    case 'prove':
      content = <ProvePage />;
      break;
    case 'help':
      content = <HelpPage />;
      break;
    case 'card':
      content = <CardPage />;
      break;
    case 'evidence':
      content = <EvidencePage />;
      break;
    case 'people':
      content = <PeoplePage />;
      break;
    default:
      content = <BoardPage />;
  }
  return (
    <HouseholdContext.Provider value={ctx}>
      <div className={`app app-${page}`}>
        <a href="#main" className="skip-link">
          {d.landing.skip}
        </a>
        <TopBar back={back} />
        {!online && <p className="offline-bar">{d.common.offline}</p>}
        <main id="main" className="app-main" tabIndex={-1}>
          {content}
        </main>
        <BottomNav current={page === 'task' || page === 'review' || page === 'evidence' || page === 'people' ? '' : page} />
      </div>
    </HouseholdContext.Provider>
  );
}
