import type { Board, Claim, HelpResult, Health, LedgerEvent, LeftOut, Person, ProofResult, Recording } from './types';

const TOKENS = 'iid.tokens';
const LAST = 'iid.last';

function readTokens(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(TOKENS) || '{}') as Record<string, string>;
  } catch {
    return {};
  }
}

const memory: Record<string, string> = {};

export function getToken(household: string): string | null {
  return memory[household] || readTokens()[household] || null;
}

export function setToken(household: string, token: string): void {
  memory[household] = token;
  try {
    const all = readTokens();
    all[household] = token;
    localStorage.setItem(TOKENS, JSON.stringify(all));
    localStorage.setItem(LAST, household);
  } catch {
    /* private mode: keep it in memory for this visit */
  }
}

export function forgetHousehold(household: string): void {
  delete memory[household];
  try {
    const all = readTokens();
    delete all[household];
    localStorage.setItem(TOKENS, JSON.stringify(all));
    if (localStorage.getItem(LAST) === household) localStorage.removeItem(LAST);
  } catch {
    /* ignore */
  }
}

export function lastHousehold(): string | null {
  try {
    const id = localStorage.getItem(LAST);
    return id && getToken(id) ? id : null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  code: string;
  /** For a video sent in pieces: how much of it the server has. */
  received?: number;
  constructor(status: number, message: string, code = '', received?: number) {
    super(message);
    this.status = status;
    this.code = code;
    this.received = received;
  }
}

type Opts = { method?: string; json?: unknown; form?: FormData; household?: string; token?: string; signal?: AbortSignal; headers?: Record<string, string> };

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers };
  const token = opts.token ?? (opts.household ? getToken(opts.household) : null);
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  let res: Response;
  try {
    res = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers, body, signal: opts.signal });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError(0, 'offline', 'offline');
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const d = data as { detail?: unknown; error?: string; received?: number } | null;
    const detail = typeof d?.detail === 'string' ? d.detail : Array.isArray(d?.detail) ? 'Please check the form.' : res.statusText;
    throw new ApiError(res.status, detail || 'Error', d?.error || '', typeof d?.received === 'number' ? d.received : undefined);
  }
  return data as T;
}

const h = (id: string) => `/api/h/${encodeURIComponent(id)}`;

export function mediaUrl(household: string, rel: string, token?: string | null): string {
  const t = token ?? getToken(household);
  return `${h(household)}/media/${rel.split('/').map(encodeURIComponent).join('/')}${t ? `?t=${encodeURIComponent(t)}` : ''}`;
}

export const Api = {
  health: () => api<Health>('/api/health'),
  policy: () => api<{ policy: Record<string, unknown>; sha256: string; pinned: string }>('/api/policy'),
  startDemo: () => api<{ household_id: string; token: string }>('/api/demo/start', { method: 'POST' }),
  /** A real home. On an invite-only server the invite code goes in X-Admin-Token. */
  createHousehold: (body: { name: string; leaving_name: string; language: 'en' | 'si'; absence_start?: string; absence_end?: string }, invite?: string) =>
    api<{ household_id: string; token: string }>('/api/households', { json: body, headers: invite ? { 'X-Admin-Token': invite } : undefined }),
  openLink: (token: string) =>
    api<{ kind: 'owner' | 'person' | 'sticker'; household_id: string; person_id: string | null; task_key: string | null; token: string; task?: Board['tasks'][number] | null; household?: Board['household']; contacts?: HelpResult['contacts'] }>(
      `/api/s/${encodeURIComponent(token)}`,
    ),
  board: (id: string, minutes = 20, on?: string) => api<Board>(`${h(id)}/board?minutes=${minutes}${on ? `&on=${on}` : ''}`, { household: id }),
  claims: (id: string) => api<{ claims: Claim[]; recordings: Record<string, { id: string; kind: string; lang: string; duration: number }>; left_out: LeftOut[] }>(`${h(id)}/claims`, { household: id }),
  decide: (id: string, claimId: string, decision: 'accepted' | 'rejected', text?: { text_en?: string; text_si?: string }) =>
    api<{ claim: Claim }>(`${h(id)}/claims/${encodeURIComponent(claimId)}/decide`, { household: id, json: { decision, ...text } }),
  /** With `task`, the recording as that job shows it: its own clip and still (what family members and stickers get). */
  recording: (id: string, rid: string, token?: string, task?: string) =>
    api<Recording>(`${h(id)}/recordings/${encodeURIComponent(rid)}${task ? `?task=${encodeURIComponent(task)}` : ''}`, { household: id, token }),
  job: (id: string, job: string) => api<{ status: string; step?: { name: string; detail: string }; steps?: { name: string; detail: string; at?: string }[]; error?: string; code?: string; recording_id?: string }>(`${h(id)}/jobs/${encodeURIComponent(job)}`, { household: id }),
  addPerson: (id: string, p: { name: string; role: 'staying' | 'helper'; language: 'en' | 'si'; relation?: string; whatsapp?: string | null }) =>
    api<{ person: Person }>(`${h(id)}/people`, { household: id, json: p }),
  updatePerson: (id: string, pid: string, p: Partial<Pick<Person, 'name' | 'language' | 'relation' | 'whatsapp'>>) =>
    api<{ person: Person }>(`${h(id)}/people/${encodeURIComponent(pid)}`, { household: id, method: 'PATCH', json: p }),
  removePerson: (id: string, pid: string) => api<{ ok: boolean }>(`${h(id)}/people/${encodeURIComponent(pid)}`, { household: id, method: 'DELETE' }),
  setAbsence: (id: string, start: string, end: string) => api<{ ok: boolean }>(`${h(id)}/absence`, { household: id, json: { start, end } }),
  show: (id: string, form: FormData) => api<ProofResult>(`${h(id)}/proofs/show`, { household: id, form }),
  tell: (id: string, form: FormData) => api<ProofResult>(`${h(id)}/proofs/tell`, { household: id, form }),
  help: (id: string, question: string, lang: 'en' | 'si') => api<HelpResult>(`${h(id)}/help`, { household: id, json: { question, lang } }),
  helpVoice: (id: string, form: FormData) => api<HelpResult>(`${h(id)}/help/voice`, { household: id, form }),
  answerGap: (id: string, form: FormData) => api<Record<string, unknown>>(`${h(id)}/gaps/answer`, { household: id, form }),
  evidence: (id: string, limit = 400) => api<{ chain_ok: boolean; broken_at: number | null; events: LedgerEvent[]; count: number }>(`${h(id)}/evidence?limit=${limit}`, { household: id }),
  links: (id: string) =>
    api<{ people: { person_id: string; name: string; url: string; token: string }[]; stickers: { task_key: string; title_en: string; title_si: string; url: string; token: string; safety: string }[]; version: number }>(
      `${h(id)}/links`,
      { household: id },
    ),
  rotate: (id: string) => api<{ token: string }>(`${h(id)}/links/rotate`, { household: id, method: 'POST' }),
  erase: (id: string) => api<{ ok: boolean }>(`${h(id)}`, { household: id, method: 'DELETE' }),
  samples: (id: string) =>
    api<{ show: { id: string; task_key: string; photo: string | null }[]; tell: { id: string; task_key: string; person_id: string | null; lang: 'en' | 'si'; transcript: string }[]; help: string[] }>(`${h(id)}/samples`, {
      household: id,
    }),
  simulate: (id: string, person_id: string, text: string, lang: 'en' | 'si') =>
    api<{ replies: string[]; result: HelpResult }>(`${h(id)}/whatsapp/simulate`, {
      household: id,
      json: { person_id, text, lang },
    }),
};

/** Send one piece of a video, with progress. Rejects with ApiError, carrying `received` on a 409. */
function sendPiece(url: string, piece: Blob, token: string | null, onProgress: (bytes: number) => void): Promise<{ received: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onerror = () => reject(new ApiError(0, 'offline', 'offline'));
    xhr.onload = () => {
      let data: { detail?: string; received?: number } | null = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && typeof data?.received === 'number') resolve({ received: data.received });
      else reject(new ApiError(xhr.status, (data && typeof data.detail === 'string' && data.detail) || xhr.statusText, '', typeof data?.received === 'number' ? data.received : undefined));
    };
    xhr.send(piece);
  });
}

/** Send a video in pieces, each its own request, so no host's limit on one request matters,
    and carry on from what the server has if the connection drops. */
export async function uploadInPieces(household: string, file: File, lang: 'en' | 'si', onProgress: (fraction: number) => void): Promise<{ job_id: string }> {
  const start = await api<{ upload_id: string; chunk_bytes: number; received: number }>(`${h(household)}/uploads`, { household, json: { size: file.size, lang, name: file.name } });
  const url = `${h(household)}/uploads/${encodeURIComponent(start.upload_id)}`;
  const step = Math.max(64 * 1024, start.chunk_bytes);
  let offset = start.received;
  let failures = 0;
  while (offset < file.size) {
    const at = offset;
    try {
      const res = await sendPiece(`${url}?offset=${at}`, file.slice(at, Math.min(file.size, at + step)), getToken(household), (sent) => onProgress(Math.min(1, (at + sent) / file.size)));
      offset = res.received;
      failures = 0;
    } catch (err) {
      const e = err as ApiError;
      if (e.status === 409 && typeof e.received === 'number') {
        offset = e.received; // that piece had arrived; carry on from the server's count
        continue;
      }
      if (e.status && e.status !== 429 && e.status < 500) throw err;
      failures += 1;
      if (failures > 5) throw err;
      await new Promise((r) => window.setTimeout(r, 1500 * failures));
    }
  }
  onProgress(1);
  return api<{ job_id: string }>(`${url}/finish`, { household, method: 'POST' });
}
