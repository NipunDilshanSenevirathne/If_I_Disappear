import { Copy, House, Users, Video } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Loading, messageOf, useToast } from '../components/Common';
import { useI18n } from '../i18n';
import { Api, ApiError, setToken } from '../lib/api';
import { useHealth } from '../lib/health';
import { Link } from '../lib/router';
import { PublicFrame } from './Public';

/** Start a real home: only on a server with a Meta Model API key, and with its invite code
    when it is invite-only (the default), so a public copy can't run up its owner's bill. */
export function StartPage() {
  const { d, lang: uiLang } = useI18n();
  const s = d.start;
  const toast = useToast();
  const health = useHealth();
  const [name, setName] = useState('');
  const [leaving, setLeaving] = useState('');
  const [lang, setLang] = useState<'en' | 'si'>(uiLang);
  const [leaves, setLeaves] = useState('');
  const [returns, setReturns] = useState('');
  const [invite, setInvite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState<{ id: string; link: string } | null>(null);

  if (!health)
    return (
      <PublicFrame title={s.title}>
        <Loading />
      </PublicFrame>
    );

  if (health.mode !== 'live')
    return (
      <PublicFrame title={s.title}>
        <p className="lead start-judge">{s.judgeOnly}</p>
        <Link to="/try" className="btn btn-primary">
          {d.landing.heroCta}
        </Link>
      </PublicFrame>
    );

  if (ready) {
    const copy = async () => {
      try {
        await navigator.clipboard.writeText(ready.link);
        toast(s.copied, 'ok');
      } catch {
        /* the link stays on screen to copy by hand */
      }
    };
    return (
      <PublicFrame title={s.readyTitle}>
        <p className="lead">{s.readyBody}</p>
        <div className="card owner-link-card">
          <code className="owner-link">{ready.link}</code>
          <button type="button" className="btn btn-sm" onClick={copy}>
            <Copy aria-hidden />
            {s.copy}
          </button>
        </div>
        <div className="start-next">
          <Link to={`/h/${ready.id}/record`} className="btn btn-primary">
            <Video aria-hidden />
            {s.recordFirst}
          </Link>
          <Link to={`/h/${ready.id}/people`} className="btn">
            <Users aria-hidden />
            {s.addPeople}
          </Link>
        </div>
      </PublicFrame>
    );
  }

  const needInvite = !!health.invite_only;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const dates = leaves && returns ? { absence_start: leaves, absence_end: returns } : {};
      const res = await Api.createHousehold({ name: name.trim(), leaving_name: leaving.trim(), language: lang, ...dates }, needInvite ? invite.trim() : undefined);
      setToken(res.household_id, res.token);
      setReady({ id: res.household_id, link: `${location.origin}/l/${res.token}` });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? s.badInvite : messageOf(err, d.common.error, d.errors));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PublicFrame title={s.title}>
      <p className="lead">{s.body}</p>
      <form className="card start-form" onSubmit={submit}>
        <label className="field">
          <span>{s.name}</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={s.namePlaceholder} required maxLength={80} />
        </label>
        <label className="field">
          <span>{s.leaving}</span>
          <input className="input" value={leaving} onChange={(e) => setLeaving(e.target.value)} required maxLength={60} aria-describedby="leaving-hint" />
          <small className="help-text" id="leaving-hint">
            {s.leavingHint}
          </small>
        </label>
        <fieldset className="field">
          <legend className="label">{s.lang}</legend>
          <div className="seg">
            {(['si', 'en'] as const).map((l) => (
              <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
                {d.lang[l]}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="start-dates">
          <label className="field">
            <span>{s.leaves}</span>
            <input type="date" className="input" value={leaves} onChange={(e) => setLeaves(e.target.value)} />
          </label>
          <label className="field">
            <span>{s.returns}</span>
            <input type="date" className="input" value={returns} min={leaves || undefined} onChange={(e) => setReturns(e.target.value)} />
          </label>
        </div>
        {needInvite && (
          <label className="field">
            <span>{s.invite}</span>
            <input className="input" value={invite} onChange={(e) => setInvite(e.target.value)} required autoComplete="off" spellCheck={false} aria-describedby="invite-hint" />
            <small className="help-text" id="invite-hint">
              {s.inviteHint}
            </small>
          </label>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-dark btn-block" disabled={busy || !name.trim() || !leaving.trim() || (needInvite && !invite.trim())}>
          <House aria-hidden />
          {busy ? s.creating : s.create}
        </button>
      </form>
    </PublicFrame>
  );
}
