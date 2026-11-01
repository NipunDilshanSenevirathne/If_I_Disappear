import { ArrowLeft, ShieldCheck } from 'lucide-react';
import { ErrorState, Loading } from '../components/Common';
import { Logo } from '../components/Logo';
import { LangToggle } from '../components/Shell';
import { format, useI18n } from '../i18n';
import { Api } from '../lib/api';
import { FONTS, GENERATED, LIBRARIES, PHOTOS } from '../lib/credits';
import { useAsync } from '../lib/hooks';
import { Link } from '../lib/router';
import type { ReactNode } from 'react';

export function PublicFrame({ title, children }: { title: string; children: ReactNode }) {
  const { d } = useI18n();
  return (
    <div className="public">
      <header className="public-top">
        <Link to="/" className="public-home" aria-label={d.link.home}>
          <Logo light size={28} />
        </Link>
        <LangToggle dark />
      </header>
      <main id="main" className="public-main">
        <Link to="/" className="back-link">
          <ArrowLeft aria-hidden />
          {d.common.back}
        </Link>
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  );
}

export function RulesPage() {
  const { d } = useI18n();
  const data = useAsync(() => Api.policy(), []);
  return (
    <PublicFrame title={d.rules.title}>
      <p className="lead">{d.rules.body}</p>
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorState error={data.error} onRetry={data.reload} />
      ) : (
        (() => {
          const p = data.data!.policy as {
            thresholds: Record<string, number>;
            required_witnesses: Record<string, string[]>;
            blocked_topics: { en: string[]; si: string[] };
            never_store: string[];
          };
          const t = p.thresholds;
          const ok = data.data!.sha256 === data.data!.pinned;
          return (
            <>
              <p className={`chain chain-${ok ? 'ok' : 'bad'}`}>
                <ShieldCheck aria-hidden />
                <span>
                  {ok ? d.people.policyPinned : d.people.policyChanged}
                  <code className="chain-head">SHA-256 {data.data!.sha256}</code>
                </span>
              </p>
              <h2>{d.rules.witnessesTitle}</h2>
              <table className="rules-table">
                <thead>
                  <tr>
                    <th scope="col">{d.rules.kind}</th>
                    <th scope="col">{d.rules.needs}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(p.required_witnesses).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k === 'none' ? d.rules.everyday : d.safety[k as 'gas']}</td>
                      <td>{v.map((w) => d.witness[w as 'words']).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h2>{d.rules.thresholdsTitle}</h2>
              <dl className="rules-list">
                <div>
                  <dt>{d.rules.samConfidence}</dt>
                  <dd>{Math.round(t.sam_min_confidence * 100)}%</dd>
                </div>
                <div>
                  <dt>{d.rules.quoteChars}</dt>
                  <dd>{t.quote_min_chars}</dd>
                </div>
                <div>
                  <dt>{d.rules.slack}</dt>
                  <dd>
                    −{t.quote_time_slack_before_s} s / +{t.quote_time_slack_after_s} s
                  </dd>
                </div>
                <div>
                  <dt>{d.rules.showFeatures}</dt>
                  <dd>{t.show_min_matched_features}</dd>
                </div>
                <div>
                  <dt>{d.rules.tellCoverage}</dt>
                  <dd>{Math.round(t.tell_min_coverage * 100)}%</dd>
                </div>
                <div>
                  <dt>{d.rules.proofDays}</dt>
                  <dd>{t.proof_valid_days}</dd>
                </div>
                <div>
                  <dt>{d.rules.helpScore}</dt>
                  <dd>{Math.round(t.help_min_score * 100)}%</dd>
                </div>
              </dl>
              <h2>{d.rules.blockedTitle}</h2>
              <p>{d.rules.blockedBody}</p>
              <p className="word-list">{[...p.blocked_topics.en, ...p.blocked_topics.si].join(', ')}</p>
              <h2>{d.rules.neverTitle}</h2>
              <ul className="plain-list">
                {p.never_store.map((x) => (
                  <li key={x}>{d.rules.never[x as 'pin'] ?? x}</li>
                ))}
              </ul>
              <p className="help-text">
                <a href="/api/policy">{d.rules.raw}</a>
              </p>
            </>
          );
        })()
      )}
    </PublicFrame>
  );
}

export function CreditsPage() {
  const { d, lang } = useI18n();
  return (
    <PublicFrame title={d.credits.title}>
      <p className="lead">{d.credits.body}</p>
      <h2>{d.credits.photos}</h2>
      <ul className="credit-list">
        {PHOTOS.map((p) => (
          <li key={p.id}>
            <strong>{p.use}</strong>
            <span>
              {d.credits.by} {p.photographer},{' '}
              <a href={p.page || `https://images.unsplash.com/${p.id}`} rel="noopener noreferrer" target="_blank">
                Unsplash
              </a>
            </span>
          </li>
        ))}
      </ul>
      <p className="help-text">{d.credits.license}</p>
      <h2>{d.credits.generated}</h2>
      <p>{format(d.credits.generatedBody, { list: GENERATED.map((g) => g[lang]).join(', ') })}</p>
      <h2>{d.credits.fonts}</h2>
      <ul className="credit-list">
        {FONTS.map((f) => (
          <li key={f.name}>
            <strong>{f.name}</strong>
            <span>
              {f.by}, {f.license}
            </span>
          </li>
        ))}
      </ul>
      <h2>{d.credits.code}</h2>
      <ul className="credit-list">
        {LIBRARIES.map((f) => (
          <li key={f.name}>
            <strong>{f.name}</strong>
            <span>
              {f.by}, {f.license}
            </span>
          </li>
        ))}
      </ul>
    </PublicFrame>
  );
}

export function NotFoundPage() {
  const { d } = useI18n();
  return (
    <div className="center-page">
      <Logo />
      <p className="state">{d.common.notFound}</p>
      <Link to="/" className="btn">
        {d.link.home}
      </Link>
    </div>
  );
}
