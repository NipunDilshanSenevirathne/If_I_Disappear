/** The mark: a house traced the way SAM 3.1 outlines an object, with the point that started it. */
export function LogoMark({ size = 32, title }: { size?: number; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-label={title}>
      <rect width="64" height="64" rx="15" fill="#10212A" />
      <path d="M17 31.5 32 18.5l15 13V46.5H17Z" fill="rgba(247,181,71,0.16)" stroke="#F7B547" strokeWidth="3.4" strokeLinejoin="round" />
      <circle cx="32" cy="36.5" r="4.2" fill="#FFFFFF" />
      <circle cx="32" cy="36.5" r="2" fill="#10212A" />
    </svg>
  );
}

export function Logo({ light = false, size = 32 }: { light?: boolean; size?: number }) {
  return (
    <span className={`logo${light ? ' logo-light' : ''}`}>
      <LogoMark size={size} />
      <span className="logo-word">If I Disappear</span>
    </span>
  );
}
