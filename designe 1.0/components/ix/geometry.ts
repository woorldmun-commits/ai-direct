// Геометрия графика эталона: viewBox 0 0 500 185, ось Y сверху вниз, нулевая линия y=170, сетка y=30/70/110/150.
export const W = 500;
export const H = 185;
export const BASELINE = 170;
export const GRID = [30, 70, 110, 150];
export const TOP = 24; // верхняя точка эталонного ряда (значение 146)

export type Pt = {x: number; y: number};

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
