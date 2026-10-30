// Геометрия графика эталона: viewBox 0 0 500 185, ось Y сверху вниз, нулевая линия y=170, сетка y=30/70/110/150.
export const W = 500;
export const H = 185;
export const BASELINE = 170;
export const GRID = [30, 70, 110, 150];
export const TOP = 24; // верхняя точка эталонного ряда (значение 146)

export type Pt = {x: number; y: number};

/** Keep the original point for exact display; compare source Decimals before SVG rounding. */
export function pointExtrema<T extends {value: number | null; evidence?: {amount: string | null}}>(points: T[]): {min: T; max: T} | null {
  const available = points.filter(p => p.value !== null && Number.isFinite(p.value));
  if (!available.length) return null;
  const compare = (a: T, b: T) => {
    const left = a.evidence?.amount, right = b.evidence?.amount;
    if (left != null && right != null) {
      const places = Math.max((left.split('.')[1] ?? '').length, (right.split('.')[1] ?? '').length);
      const scaled = [left, right].map(value => { const [whole, fraction = ''] = value.split('.'); return BigInt(whole + fraction.padEnd(places, '0')); });
      return scaled[0] < scaled[1] ? -1 : scaled[0] > scaled[1] ? 1 : 0;
    }
    return a.value! - b.value!;
  };
  return available.reduce((bounds, point) => ({min: compare(point, bounds.min) < 0 ? point : bounds.min, max: compare(point, bounds.max) > 0 ? point : bounds.max}), {min: available[0], max: available[0]});
}

// Controls stay within each interval: the curve passes through every observation without overshoot.
export function curvePath(points: string): string {
  const coords = points.split(' ').map(p => p.split(',').map(Number));
  return coords.map(([x, y], i) => {
    if (!i) return `M${x},${y}`;
    const [px, py] = coords[i - 1], mid = (px + x) / 2;
    return `C${mid},${py} ${mid},${y} ${x},${y}`;
  }).join(' ');
}

export const xAt = (i: number, n: number) => (n <= 1 ? 0 : (i * W) / (n - 1));

/** Масштаб «значение → пиксели viewBox». В эталоне значения заданы сразу в пикселях (scale = 1). */
export function scaleFor(values: (number | null)[], fit = true): number {
  if (!fit) return 1;
  const max = Math.max(0, ...values.filter((v): v is number => v !== null));
  return max > 0 ? (BASELINE - TOP) / max : 1;
}

/** Серия → непрерывные отрезки; null разрывает линию (не превращается в 0 и не интерполируется). */
export function segments(values: (number | null)[], scale: number): string[] {
  const out: string[] = [];
  let run: string[] = [];
  const flush = () => { if (run.length > 1) out.push(run.join(' ')); else if (run.length === 1) out.push(run[0] + ' ' + run[0]); run = []; };
  values.forEach((v, i) => {
    if (v === null) { flush(); return; }
    run.push(`${xAt(i, values.length)},${BASELINE - v * scale}`);
  });
  flush();
  return out;
}
