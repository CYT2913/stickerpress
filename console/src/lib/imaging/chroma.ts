/**
 * 背景透明化（与 Python 引擎 stickerpress/imaging/chroma.py 同算法）。
 *
 * 优先级：真 alpha > 色度键。
 * 生成模型（含 ChatGPT 贴纸）导出的 PNG 往往自带真透明通道——查看器里那层
 * 灰白棋格只是底衬，不在文件里。有 alpha 就直通，不做任何色度键：没有溢色
 * 抑制、没有阈值损失，连通域切分更准。
 *
 * 只有拿不到 alpha 时才退回品红兜底：让模型在纯 #FF00FF 上作画，这里键掉。
 * 注意第三种情况——模型把棋盘格"画"出来的假透明，既没有 alpha 也键不掉，
 * 只能重出图（判别见 engine/tools/check_alpha.py）。
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
  return transparentRatio(src) > 0.1;
}

/**
 * 全透明像素占比（alpha < 16）。抽样步长 7，够快也够准。
 *
 * 注意"有 alpha 通道"不等于"有透明像素"：ImageData 恒有第 4 通道，
 * 所以只能靠实际透明像素比例判断，不能靠通道存在性。
 */
export function transparentRatio(src: ImageData): number {
  const n = src.width * src.height;
  let transparent = 0;
  let sampled = 0;
  for (let i = 0; i < n; i += 7) {
    if (src.data[i * 4 + 3] < 16) transparent++;
    sampled++;
  }
  return sampled === 0 ? 0 : transparent / sampled;
}
