/**
 * alpha 通道 → 矢量刀版轮廓（die-cut CutContour）。
 *
 * 这一步决定产物是不是"真 SVG"。只把 PNG 塞进 <image> 的 SVG 对印厂毫无用处——
 * 模切机需要的是一条闭合矢量路径告诉它刀往哪走。
 *
 * alpha → 二值化 → 填洞 → 外扩白边 → 平滑 → Moore 边界追踪
 *       → RDP 抽稀 → 等弧长重采样 → Catmull-Rom 转三次贝塞尔
 */

import {
  type Mask,
  close,
  connectedComponents,
  dilate,
  fillHoles,
  makeMask,
  smoothThreshold,
} from './mask';

export type Point = [number, number];

// Moore 邻域，顺时针：W, NW, N, NE, E, SE, S, SW
const MOORE: Point[] = [
  [-1, 0],
  [-1, -1],
  [0, -1],
  [1, -1],
  [1, 0],
  [1, 1],
  [0, 1],
  [-1, 1],
];

function mooreIndex(dx: number, dy: number): number {
  for (let i = 0; i < 8; i++)
    if (MOORE[i][0] === dx && MOORE[i][1] === dy) return i;
  return 0;
}

export function buildCutMask(
  alpha: Uint8Array,
  w: number,
  h: number,
  threshold = 24,
  offsetPx = 0,
  smoothR = 2,
): Mask {
  let m = makeMask(w, h);
  for (let i = 0; i < w * h; i++) m.data[i] = alpha[i] > threshold ? 1 : 0;
  m = fillHoles(m);
  if (offsetPx > 0) m = dilate(m, offsetPx);
  m = close(m, 2); // 填掉毛刺凹槽，模切刀走不了像素级锯齿
  if (smoothR > 0) m = smoothThreshold(m, smoothR, 0.5);
  return fillHoles(m);
}

/** Moore 邻域边界追踪，返回外轮廓点序列（顺时针） */
export function traceOuterBoundary(mask: Mask, maxSteps = 400000): Point[] {
  const { comps, labels } = connectedComponents(mask);
  if (!comps.length) return [];
  // 只追最大连通域，避免被残留碎片带偏
  const biggest = comps.reduce((a, b) => (b.area > a.area ? b : a));

  const w = mask.w + 2;
  const h = mask.h + 2;
  const pad = new Uint8Array(w * h);
  for (let y = 0; y < mask.h; y++)
    for (let x = 0; x < mask.w; x++)
      if (labels[y * mask.w + x] === biggest.label)
        pad[(y + 1) * w + (x + 1)] = 1;

  let start: Point | null = null;
  for (let i = 0; i < w * h && !start; i++)
    if (pad[i]) start = [i % w, (i / w) | 0];
  if (!start) return [];

  const solid = (p: Point) => {
    const x = p[0];
    const y = p[1];
    return x >= 0 && y >= 0 && x < w && y < h && pad[y * w + x] === 1;
  };

  const contour: Point[] = [start];
  let current: Point = start;
  let backtrack = 0; // 起点是行优先第一个前景点，其西侧必为背景
  let second: Point | null = null;

  for (let step = 0; step < maxSteps; step++) {
    let found = false;
    for (let k = 1; k <= 8; k++) {
      const idx = (backtrack + k) % 8;
      const cand: Point = [
        current[0] + MOORE[idx][0],
        current[1] + MOORE[idx][1],
      ];
      if (solid(cand)) {
        backtrack = mooreIndex(current[0] - cand[0], current[1] - cand[1]);
        current = cand;
        found = true;
        break;
      }
    }
    if (!found) break; // 孤立像素
    if (!second) {
      second = current;
      contour.push(current);
      continue;
    }
    // Jacob 停止条件：再次回到起点
    if (current[0] === start[0] && current[1] === start[1]) break;
    contour.push(current);
  }
  return contour.map(([x, y]) => [x - 1, y - 1] as Point);
}

/** Ramer–Douglas–Peucker 抽稀（迭代实现，避免深递归） */
export function rdp(points: Point[], epsilon: number): Point[] {
  const n = points.length;
  if (n < 3) return points;
  const keep = new Uint8Array(n);
  keep[0] = 1;
  keep[n - 1] = 1;
  const stack: [number, number][] = [[0, n - 1]];
  while (stack.length) {
    const [i, j] = stack.pop() as [number, number];
    if (j <= i + 1) continue;
    const [x0, y0] = points[i];
    const [x1, y1] = points[j];
    const ex = x1 - x0;
    const ey = y1 - y0;
    const L = Math.hypot(ex, ey);
    let best = -1;
    let bestD = -1;
    for (let k = i + 1; k < j; k++) {
      const [px, py] = points[k];
      const d =
        L < 1e-9
          ? Math.hypot(px - x0, py - y0)
          : Math.abs(ex * (y0 - py) - (x0 - px) * ey) / L;
      if (d > bestD) {
        bestD = d;
        best = k;
      }
    }
    if (bestD > epsilon && best > 0) {
      keep[best] = 1;
      stack.push([i, best], [best, j]);
    }
  }
  return points.filter((_, i) => keep[i] === 1);
}

/** 按弧长均匀重采样闭合折线，让后续平滑更稳定 */
export function resampleClosed(points: Point[], step: number): Point[] {
  if (points.length < 3) return points;
  const pts = [...points, points[0]];
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(
      cum[i - 1] +
        Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]),
    );
  }
  const total = cum[cum.length - 1];
  if (total < 1e-6) return points;
  const n = Math.max(Math.floor(total / Math.max(step, 1e-6)), 8);
  const out: Point[] = [];
  let seg = 0;
  for (let i = 0; i < n; i++) {
    const t = (total * i) / n;
    while (seg < cum.length - 2 && cum[seg + 1] < t) seg++;
    const span = cum[seg + 1] - cum[seg];
    const r = span < 1e-9 ? 0 : (t - cum[seg]) / span;
    out.push([
      pts[seg][0] + (pts[seg + 1][0] - pts[seg][0]) * r,
      pts[seg][1] + (pts[seg + 1][1] - pts[seg][1]) * r,
    ]);
  }
  return out;
}

/** 闭合折线 → 三次贝塞尔 SVG path（Catmull-Rom 转 Bezier） */
export function toBezierPath(
  points: Point[],
  tension = 1,
  precision = 3,
): string {
  const n = points.length;
  if (n < 3) return '';
  const f = (v: number) => v.toFixed(precision);
  const fmt = (p: Point) => `${f(p[0])} ${f(p[1])}`;
  const k = tension / 6;
  const d: string[] = [`M ${fmt(points[0])}`];
  for (let i = 0; i < n; i++) {
    const p0 = points[(i - 1 + n) % n];
    const p1 = points[i];
    const p2 = points[(i + 1) % n];
    const p3 = points[(i + 2) % n];
    const c1: Point = [
      p1[0] + (p2[0] - p0[0]) * k,
      p1[1] + (p2[1] - p0[1]) * k,
    ];
    const c2: Point = [
      p2[0] - (p3[0] - p1[0]) * k,
      p2[1] - (p3[1] - p1[1]) * k,
    ];
    d.push(`C ${fmt(c1)}, ${fmt(c2)}, ${fmt(p2)}`);
  }
  d.push('Z');
  return d.join(' ');
}

/** 一步到位：alpha → (SVG path d, 轮廓点)，坐标单位仍是像素 */
export function alphaToCutPath(
  alpha: Uint8Array,
  w: number,
  h: number,
  opts: {
    offsetPx?: number;
    simplifyPx?: number;
    resamplePx?: number;
    smoothR?: number;
  } = {},
): { d: string; points: Point[] } {
  const mask = buildCutMask(
    alpha,
    w,
    h,
    24,
    opts.offsetPx ?? 0,
    opts.smoothR ?? 2,
  );
  const raw = traceOuterBoundary(mask);
  if (raw.length < 8) {
    const rect: Point[] = [
      [0, 0],
      [w - 1, 0],
      [w - 1, h - 1],
      [0, h - 1],
    ];
    return { d: toBezierPath(rect), points: rect };
  }
  const simple = rdp(raw, opts.simplifyPx ?? 1.6);
  const even = resampleClosed(simple, opts.resamplePx ?? 7);
  return { d: toBezierPath(even), points: even };
}

export function transformPoints(
  points: Point[],
  scale: number,
  dx: number,
  dy: number,
): Point[] {
  return points.map(([x, y]) => [x * scale + dx, y * scale + dy] as Point);
}

/** 两条轮廓间的最小距离（抽样近似），用于校验刀版净距 */
export function minDistanceBetween(
  a: Point[],
  b: Point[],
  sample = 120,
): number {
  if (!a.length || !b.length) return Number.POSITIVE_INFINITY;
  const pick = (arr: Point[]) =>
    arr.length <= sample
      ? arr
      : Array.from(
          { length: sample },
          (_, i) => arr[Math.round((i * (arr.length - 1)) / (sample - 1))],
        );
  const A = pick(a);
  const B = pick(b);
  let best = Number.POSITIVE_INFINITY;
  for (const [ax, ay] of A) {
    for (const [bx, by] of B) {
      const d = (ax - bx) ** 2 + (ay - by) ** 2;
      if (d < best) best = d;
    }
  }
  return Math.sqrt(best);
}
