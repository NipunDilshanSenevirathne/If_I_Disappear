import { Pencil, Plus, ShieldCheck, Trash2, UserRound } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { messageOf, Section, useToast } from '../components/Common';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { format, useI18n } from '../i18n';
import { Api, forgetHousehold } from '../lib/api';
import { forgetOffline } from '../lib/offline';
import { useAsync } from '../lib/hooks';
import { navigate } from '../lib/router';
import type { Person } from '../lib/types';

function PersonRow({ person, owner }: { person: Person; owner: boolean }) {
  const { id, refresh } = useHousehold();
  const { d } = useI18n();
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [lang, setLang] = useState(person.language);
  const [relation, setRelation] = useState(person.relation);
  const [whatsapp, setWhatsapp] = useState(person.whatsapp || '');
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await Api.updatePerson(id, person.id, { language: lang, relation, whatsapp: whatsapp || null });
      await refresh();
      setEdit(false);
      toast(d.common.saved, 'ok');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(format(d.people.removeConfirm, { name: person.name }))) return;
    try {
      await Api.removePerson(id, person.id);
      await refresh();
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    }
  };
  return (
    <li className="person-row">
      <div className="person-line">
        <UserRound aria-hidden />
        <span className="person-name">
          <strong>{person.name}</strong>
          <span className="help-text">{[person.relation, d.people[person.role]].filter(Boolean).join(', ')}</span>
        </span>
        <span className="chip">{d.lang[person.language]}</span>
        {owner && person.role !== 'leaving' && !edit && (
          <button type="button" className="icon-btn" onClick={() => setEdit(true)} aria-label={format(d.people.edit, { name: person.name })}>
            <Pencil aria-hidden />
          </button>
        )}
      </div>
      {edit && (
        <form className="person-edit" onSubmit={save}>
          <label className="field">
            <span>{d.people.relation}</span>
            <input className="input" value={relation} onChange={(e) => setRelation(e.target.value)} maxLength={40} />
          </label>
          <label className="field">
            <span>{d.people.language}</span>
            <select className="select" value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'si')}>
              <option value="si">සිංහල</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className="field">
            <span>{d.people.whatsapp}</span>
            <input className="input" value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} inputMode="tel" placeholder="94771234567" />
            <span className="help-text">{d.people.whatsappHelp}</span>
          </label>
          <div className="row-actions">
            <button type="button" className="btn btn-quiet" onClick={remove}>
              <Trash2 aria-hidden />
              {d.people.remove}
            </button>
            <span className="spacer" />
            <button type="button" className="btn" onClick={() => setEdit(false)}>
              {d.common.cancel}
            </button>
            <button type="submit" className="btn btn-dark" disabled={busy}>
              {d.common.save}
            </button>
          </div>
        </form>
      )}
    </li>
  );
}

function AddPerson() {
  const { id, refresh } = useHousehold();
  const { d } = useI18n();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [relation, setRelation] = useState('');
  const [role, setRole] = useState<'staying' | 'helper'>('staying');
  const [lang, setLang] = useState<'en' | 'si'>('si');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await Api.addPerson(id, { name, relation, role, language: lang });
      await refresh();
      setOpen(false);
      setName('');
      setRelation('');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    }
  };
  if (!open)
    return (
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        <Plus aria-hidden />
        {d.people.add}
      </button>
    );
  return (
    <form className="card person-add" onSubmit={submit}>
      <label className="field">
        <span>{d.people.name}</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} />
      </label>
      <label className="field">
        <span>{d.people.relation}</span>
        <input className="input" value={relation} onChange={(e) => setRelation(e.target.value)} maxLength={40} />
      </label>
      <fieldset className="field">
        <legend className="label">{d.people.roleLabel}</legend>
        <div className="seg">
          {(['staying', 'helper'] as const).map((r) => (
            <button key={r} type="button" aria-pressed={role === r} onClick={() => setRole(r)}>
              {d.people[r]}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="field">
        <span>{d.people.language}</span>
        <select className="select" value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'si')}>
          <option value="si">සිංහල</option>
          <option value="en">English</option>
        </select>
      </label>
      <div className="row-actions">
        <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>
          {d.common.cancel}
        </button>
        <button type="submit" className="btn btn-dark" disabled={!name.trim()}>
          {d.people.add}
        </button>
      </div>
    </form>
  );
}

function Dates() {
  const { id, board, refresh } = useHousehold();
  const { d } = useI18n();
  const toast = useToast();
  const [start, setStart] = useState(board.household.absence?.start || '');
  const [end, setEnd] = useState(board.household.absence?.end || '');
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await Api.setAbsence(id, start, end);
      await refresh();
      toast(d.common.saved, 'ok');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    }
  };
  return (
    <form className="card dates" onSubmit={save}>
      <label className="field">
        <span>{d.people.leaves}</span>
        <input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} required />
      </label>
      <label className="field">
        <span>{d.people.returns}</span>
        <input type="date" className="input" value={end} min={start} onChange={(e) => setEnd(e.target.value)} required />
      </label>
      <button type="submit" className="btn btn-dark" disabled={!start || !end}>
        {d.people.saveDates}
      </button>
    </form>
  );
}

function Rules() {
  const { d } = useI18n();
  const data = useAsync(() => Api.policy(), []);
  if (!data.data) return null;
  const t = data.data.policy.thresholds as Record<string, number>;
  const match = data.data.sha256 === data.data.pinned;
  return (
    <div className="card rules">
      <p className={`chain chain-${match ? 'ok' : 'bad'}`}>
        <ShieldCheck aria-hidden />
        <span>
          {match ? d.people.policyPinned : d.people.policyChanged}
          <code className="chain-head">{data.data.sha256.slice(0, 16)}…</code>
        </span>
      </p>
      <dl className="rules-list">
        <div>
          <dt>{d.rules.samConfidence}</dt>
          <dd>{Math.round(t.sam_min_confidence * 100)}%</dd>
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
          <dt>{d.rules.safety}</dt>
          <dd>{d.rules.safetyValue}</dd>
        </div>
      </dl>
    </div>
  );
}

export function PeoplePage() {
  const { id, board } = useHousehold();
  const { d } = useI18n();
  const toast = useToast();
  const owner = board.you.role === 'owner';
  const [confirm, setConfirm] = useState('');
  const erase = async () => {
    try {
      await Api.erase(id);
      await forgetOffline(id);
      forgetHousehold(id);
      toast(d.people.deleted, 'ok');
      navigate('/');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    }
  };
  return (
    <>
      <SampleBanner />
      <PageTitle title={owner ? d.people.title : d.menu.settings} />
      <Section id="people" title={d.people.peopleTitle}>
        <ul className="people">
          {board.people.map((p) => (
            <PersonRow key={p.id} person={p} owner={owner} />
          ))}
        </ul>
        {owner && <AddPerson />}
      </Section>
      {owner && (
        <Section id="dates" title={d.people.absence}>
          <Dates />
        </Section>
      )}
      <Section id="rules" title={d.people.policy}>
        <p className="section-lead">{d.people.policyBody}</p>
        <Rules />
      </Section>
      <Section id="device" title={d.people.deviceTitle}>
        <div className="card device-zone">
          <p className="help-text">{d.people.deviceBody}</p>
          <button
            type="button"
            className="btn"
            onClick={async () => {
              await forgetOffline(id);
              forgetHousehold(id);
              toast(d.people.deviceForgotten, 'info');
              navigate('/');
            }}
          >
            {d.people.deviceForget}
          </button>
        </div>
      </Section>
      {owner && (
        <Section id="danger" title={d.people.danger}>
          <div className="card danger-zone">
            <p>
              <strong>{d.people.delete}</strong>
              <span className="help-text"> {d.people.deleteBody}</span>
            </p>
            <label className="field">
              <span>{d.people.deleteConfirm}</span>
              <input className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
            </label>
            <button type="button" className="btn btn-danger" disabled={confirm.trim().toUpperCase() !== 'DELETE'} onClick={erase}>
              <Trash2 aria-hidden />
              {d.people.delete}
            </button>
          </div>
        </Section>
      )}
    </>
  );
}
