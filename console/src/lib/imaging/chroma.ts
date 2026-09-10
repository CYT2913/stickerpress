/**
 * 色度键抠图（与 Python 引擎 stickerpress/imaging/chroma.py 同算法）。
 *
 * 生成模型不会输出真 alpha，要求"透明背景"时它会把棋盘格画出来。
 * 所以强制模型在纯品红 #FF00FF 上作画，这里再把背景键掉。
 */

import { type Mask, connectedComponents, makeMask } from './mask';

export const CHROMA_KEY: [number, number, number] = [255, 0, 255];

export interface KeyResult {
  rgba: ImageData;
  backgroundRatio: number;
  keyed: boolean;
}

/**
 * @param hard 距离 < hard 判为纯背景
 * @param soft 距离 > soft 判为纯前景；中间线性过渡，保住抗锯齿边缘
 */
export function chromaKey(
  src: ImageData,
  key: [number, number, number] = CHROMA_KEY,
  hard = 72,
  soft = 118,
  despill = true,
): KeyResult {
  const { width: w, height: h, data } = src;
  const n = w * h;
  const dist = new Float32Array(n);
  const bgish: Mask = makeMask(w, h);

  for (let i = 0; i < n; i++) {
    const dr = data[i * 4] - key[0];
    const dg = data[i * 4 + 1] - key[1];
    const db = data[i * 4 + 2] - key[2];
    const d = Math.sqrt(dr * dr + dg * dg + db * db);
    dist[i] = d;
    bgish.data[i] = d < soft ? 1 : 0;
  }

  // 连通性约束：只有与画布边缘连通的背景才去掉，
  // 避免主体内部恰好出现接近键色的颜色时被打穿成洞。
  const { labels, comps } = connectedComponents(bgish);
  const edge = new Set<number>();
  for (let x = 0; x < w; x++) {
    if (labels[x]) edge.add(labels[x]);
    if (labels[(h - 1) * w + x]) edge.add(labels[(h - 1) * w + x]);
  }
  for (let y = 0; y < h; y++) {
    if (labels[y * w]) edge.add(labels[y * w]);
    if (labels[y * w + w - 1]) edge.add(labels[y * w + w - 1]);
  }
  void comps;

  const out = new ImageData(w, h);
  let bgCount = 0;
  for (let i = 0; i < n; i++) {
    let a = 1;
    if (edge.has(labels[i])) {
      a = Math.min(
        1,
        Math.max(0, (dist[i] - hard) / Math.max(soft - hard, 1e-6)),
      );
    }
    let r = data[i * 4];
    const g = data[i * 4 + 1];
    let b = data[i * 4 + 2];
    if (despill && a > 0.02 && a < 0.99) {
      // 品红溢色抑制：R、B 明显高于 G 时把两者往 G 拉回
      const spill = Math.max(0, (r + b) / 2 - g);
      r = Math.max(0, r - spill * 0.85);
      b = Math.max(0, b - spill * 0.85);
    }
    const av = Math.round(a * 255);
    if (av < 8) bgCount++;
    out.data[i * 4] = r;
    out.data[i * 4 + 1] = g;
    out.data[i * 4 + 2] = b;
    out.data[i * 4 + 3] = av;
  }

  const ratio = bgCount / n;
  return { rgba: out, backgroundRatio: ratio, keyed: ratio > 0.15 };
}

/** 已带有效 alpha 的 PNG 直接放行，不做色度键 */
export function hasUsableAlpha(src: ImageData): boolean {
  const n = src.width * src.height;
  let transparent = 0;
  for (let i = 0; i < n; i += 7) {
    if (src.data[i * 4 + 3] < 16) transparent++;
  }
  return transparent / Math.ceil(n / 7) > 0.1;
}
