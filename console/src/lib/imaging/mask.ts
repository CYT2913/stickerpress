/**
 * 二值掩膜的形态学运算（积分图实现，O(N) 与核半径无关）。
 * 这是浏览器端能跑动 4K 贴纸大图的关键：朴素卷积在 r=12 时会慢两个数量级。
 */

export interface Mask {
  data: Uint8Array; // 0 / 1
  w: number;
  h: number;
}

export function makeMask(w: number, h: number): Mask {
  return { data: new Uint8Array(w * h), w, h };
}

function integral(m: Mask): Int32Array {
  const { data, w, h } = m;
  const I = new Int32Array((w + 1) * (h + 1));
  for (let y = 0; y < h; y++) {
    let rowSum = 0;
    for (let x = 0; x < w; x++) {
      rowSum += data[y * w + x];
      I[(y + 1) * (w + 1) + (x + 1)] = I[y * (w + 1) + (x + 1)] + rowSum;
    }
  }
  return I;
}

function windowStats(
  I: Int32Array,
  w: number,
  h: number,
  x: number,
  y: number,
  r: number,
) {
  const x0 = Math.max(0, x - r);
  const y0 = Math.max(0, y - r);
  const x1 = Math.min(w - 1, x + r);
  const y1 = Math.min(h - 1, y + r);
  const W = w + 1;
  const sum =
    I[(y1 + 1) * W + (x1 + 1)] -
    I[y0 * W + (x1 + 1)] -
    I[(y1 + 1) * W + x0] +
    I[y0 * W + x0];
  const area = (x1 - x0 + 1) * (y1 - y0 + 1);
  return { sum, area };
}

/** 膨胀：窗口内有任意前景则为前景 */
export function dilate(m: Mask, r: number): Mask {
  if (r <= 0) return m;
  const I = integral(m);
  const out = makeMask(m.w, m.h);
  for (let y = 0; y < m.h; y++) {
    for (let x = 0; x < m.w; x++) {
      out.data[y * m.w + x] = windowStats(I, m.w, m.h, x, y, r).sum > 0 ? 1 : 0;
    }
  }
  return out;
}

/** 腐蚀：窗口内全是前景才保留 */
export function erode(m: Mask, r: number): Mask {
  if (r <= 0) return m;
  const I = integral(m);
  const out = makeMask(m.w, m.h);
  for (let y = 0; y < m.h; y++) {
    for (let x = 0; x < m.w; x++) {
      const { sum, area } = windowStats(I, m.w, m.h, x, y, r);
      out.data[y * m.w + x] = sum === area ? 1 : 0;
    }
  }
  return out;
}

/** 闭运算：先膨胀后腐蚀，用于把贴纸周边飘散的小元素（爱心、彩带）并进主体 */
export function close(m: Mask, r: number): Mask {
  return erode(dilate(m, r), r);
}

/** 盒式模糊后再阈值化，等效于轻度高斯平滑——去掉像素级锯齿，刀版才走得动 */
export function smoothThreshold(m: Mask, r: number, ratio = 0.5): Mask {
  if (r <= 0) return m;
  const I = integral(m);
  const out = makeMask(m.w, m.h);
  for (let y = 0; y < m.h; y++) {
    for (let x = 0; x < m.w; x++) {
      const { sum, area } = windowStats(I, m.w, m.h, x, y, r);
      out.data[y * m.w + x] = sum / area > ratio ? 1 : 0;
    }
  }
  return out;
}

/** 填内部孔洞：从边界洪泛标记外部背景，剩下的背景即为孔洞 */
export function fillHoles(m: Mask): Mask {
  const { w, h } = m;
  const outside = new Uint8Array(w * h);
  const stack: number[] = [];
  const push = (i: number) => {
    if (!outside[i] && m.data[i] === 0) {
      outside[i] = 1;
      stack.push(i);
    }
  };
  for (let x = 0; x < w; x++) {
    push(x);
    push((h - 1) * w + x);
  }
  for (let y = 0; y < h; y++) {
    push(y * w);
    push(y * w + w - 1);
  }
  while (stack.length) {
    const i = stack.pop() as number;
    const x = i % w;
    const y = (i / w) | 0;
    if (x > 0) push(i - 1);
    if (x < w - 1) push(i + 1);
    if (y > 0) push(i - w);
    if (y < h - 1) push(i + w);
  }
  const out = makeMask(w, h);
  for (let i = 0; i < w * h; i++)
    out.data[i] = m.data[i] || !outside[i] ? 1 : 0;
  return out;
}

export interface Component {
  label: number;
  area: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  cx: number;
  cy: number;
}

/** 4 连通域标记 */
export function connectedComponents(m: Mask): {
  labels: Int32Array;
  comps: Component[];
} {
  const { w, h, data } = m;
  const labels = new Int32Array(w * h);
  const comps: Component[] = [];
  let next = 0;
  const stack: number[] = [];

  for (let s = 0; s < w * h; s++) {
    if (!data[s] || labels[s]) continue;
    next += 1;
    let area = 0;
    let sx = 0;
    let sy = 0;
    let x0 = w;
    let y0 = h;
    let x1 = 0;
    let y1 = 0;
    labels[s] = next;
    stack.push(s);
    while (stack.length) {
      const i = stack.pop() as number;
      const x = i % w;
      const y = (i / w) | 0;
      area += 1;
      sx += x;
      sy += y;
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
      const nb = [
        x > 0 ? i - 1 : -1,
        x < w - 1 ? i + 1 : -1,
        y > 0 ? i - w : -1,
        y < h - 1 ? i + w : -1,
      ];
      for (const j of nb) {
        if (j >= 0 && data[j] && !labels[j]) {
          labels[j] = next;
          stack.push(j);
        }
      }
    }
    comps.push({
      label: next,
      area,
      x0,
      y0,
      x1,
      y1,
      cx: sx / area,
      cy: sy / area,
    });
  }
  return { labels, comps };
}
