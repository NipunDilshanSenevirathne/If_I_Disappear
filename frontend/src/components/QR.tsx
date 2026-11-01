import QRCode from 'qrcode';
import { useMemo } from 'react';

/** A QR code drawn as one SVG path (crisp at any size, prints well). */
export function QR({ value, size = 160, label, className = '' }: { value: string; size?: number; label?: string; className?: string }) {
  const { d, n } = useMemo(() => {
    const qr = QRCode.create(value, { errorCorrectionLevel: 'M' });
    const count = qr.modules.size;
    const data = qr.modules.data;
    let path = '';
    for (let y = 0; y < count; y++) {
      let run = 0;
      for (let x = 0; x <= count; x++) {
        const on = x < count && data[y * count + x];
        if (on) run += 1;
        else if (run) {
          path += `M${x - run} ${y}h${run}v1h-${run}z`;
          run = 0;
        }
      }
    }
    return { d: path, n: count };
  }, [value]);
  const pad = 2;
  return (
    <svg className={`qr ${className}`} width={size} height={size} viewBox={`${-pad} ${-pad} ${n + pad * 2} ${n + pad * 2}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect x={-pad} y={-pad} width={n + pad * 2} height={n + pad * 2} fill="#fff" />
      <path d={d} fill="#10212A" />
    </svg>
  );
}
