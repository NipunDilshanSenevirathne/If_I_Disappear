import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from 'react';

const EVENT = 'iid:navigate';

export function navigate(to: string, opts: { replace?: boolean; keepScroll?: boolean } = {}) {
  if (to === location.pathname + location.search) {
    if (!opts.keepScroll) window.scrollTo({ top: 0 });
    return;
  }
  if (opts.replace) history.replaceState(null, '', to);
  else history.pushState(null, '', to);
  window.dispatchEvent(new Event(EVENT));
  if (!opts.keepScroll) window.scrollTo({ top: 0 });
}

export function useLocation(): { path: string; search: URLSearchParams } {
  const [, force] = useState(0);
  useEffect(() => {
    const on = () => force((n) => n + 1);
    window.addEventListener('popstate', on);
    window.addEventListener(EVENT, on);
    return () => {
      window.removeEventListener('popstate', on);
      window.removeEventListener(EVENT, on);
    };
  }, []);
  return { path: location.pathname, search: new URLSearchParams(location.search) };
}

/** Match '/h/:id/task/:key' against a path. Returns the params, or null. */
export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split('/').filter(Boolean);
  const s = path.split('/').filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(':')) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string; replace?: boolean };

export function Link({ to, replace, onClick, ...rest }: LinkProps) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || rest.target) return;
    e.preventDefault();
    navigate(to, { replace });
  };
  return <a href={to} onClick={handle} {...rest} />;
}
