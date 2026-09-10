/**
 * 把一张"六宫格贴纸大图"切成 6 张独立贴纸。
 *
 * 不用固定网格硬切——模型排布总有偏移，硬切会把耳朵、尾巴切掉。
 * 改成对 alpha 做连通域分析，让每张贴纸自己"说"它在哪，
 * 再按阅读顺序（从上到下、从左到右）编号。
 */

import { close, connectedComponents, dilate, makeMask } from './mask';

export interface StickerPiece {
  index: number;
  image: ImageData; // 裁切后的 RGBA
  bbox: [number, number, number, number];
  areaPx: number;
  centroid: [number, number];
}

export interface SplitResult {
  pieces: StickerPiece[];
  diagnostics: string[];
}

export function splitSheet(
  rgba: ImageData,
  opts: {
    expected?: number;
    rows?: number;
    alphaThreshold?: number;
    minAreaRatio?: number;
    padPx?: number;
    mergeGapPx?: number;
  } = {},
): SplitResult {
  const expected = opts.expected ?? 6;
  const rows = opts.rows ?? 3;
  const alphaThreshold = opts.alphaThreshold ?? 24;
  const minAreaRatio = opts.minAreaRatio ?? 0.004;
  const padPx = opts.padPx ?? 6;
  // 半径随图幅自适应：4K 大图用固定 9px 粘不住飘出去的爱心
  const mergeGap = opts.mergeGapPx ?? Math.max(4, Math.round(rgba.width / 260));

  const diagnostics: string[] = [];
  const { width: W, height: H, data } = rgba;
  const base = makeMask(W, H);
  for (let i = 0; i < W * H; i++)
    base.data[i] = data[i * 4 + 3] > alphaThreshold ? 1 : 0;

  // 闭运算把贴纸周边的悬浮元素并进主体，再轻微膨胀补上断裂
  let grouped = base;
  if (mergeGap > 0)
    grouped = dilate(close(base, mergeGap), Math.max(1, (mergeGap / 2) | 0));

  const { labels, comps } = connectedComponents(grouped);
  diagnostics.push(`连通域初检：${comps.length} 个`);
  if (comps.length === 0) {
    diagnostics.push('未检出任何主体，抠图可能失败');
    return { pieces: [], diagnostics };
  }

  // 面积按"原始 alpha 像素"统计，膨胀出来的虚胖不算数
  const realArea = new Map<number, number>();
  for (let i = 0; i < W * H; i++) {
    const lb = labels[i];
    if (lb && base.data[i]) realArea.set(lb, (realArea.get(lb) ?? 0) + 1);
  }

  const minArea = minAreaRatio * W * H;
  let keep = comps.filter(c => (realArea.get(c.label) ?? 0) >= minArea);
  const dropped = comps.length - keep.length;
  if (dropped)
    diagnostics.push(
      `剔除 ${dropped} 个面积过小的碎片（阈值 ${Math.round(minArea)}px）`,
    );

  keep.sort(
    (a, b) => (realArea.get(b.label) ?? 0) - (realArea.get(a.label) ?? 0),
  );
  if (keep.length > expected) {
    diagnostics.push(
      `检出 ${keep.length} 个主体，多于预期 ${expected}，保留面积最大的 ${expected} 个`,
    );
    keep = keep.slice(0, expected);
  }

  const pieces: StickerPiece[] = keep.map(c => {
    const x0 = Math.max(c.x0 - padPx, 0);
    const y0 = Math.max(c.y0 - padPx, 0);
    const x1 = Math.min(c.x1 + 1 + padPx, W);
    const y1 = Math.min(c.y1 + 1 + padPx, H);
    const cw = x1 - x0;
    const ch = y1 - y0;
    const crop = new ImageData(cw, ch);
    let area = 0;
    for (let y = 0; y < ch; y++) {
      for (let x = 0; x < cw; x++) {
        const si = (y + y0) * W + (x + x0);
        const di = y * cw + x;
        // 只保留属于本连通域的像素，抹掉邻居探进来的部分
        const own = labels[si] === c.label;
        crop.data[di * 4] = data[si * 4];
        crop.data[di * 4 + 1] = data[si * 4 + 1];
        crop.data[di * 4 + 2] = data[si * 4 + 2];
        const a = own ? data[si * 4 + 3] : 0;
        crop.data[di * 4 + 3] = a;
        if (a > alphaThreshold) area++;
      }
    }
    return {
      index: 0,
      image: crop,
      bbox: [x0, y0, x1, y1] as [number, number, number, number],
      areaPx: area,
      centroid: [c.cx, c.cy] as [number, number],
    };
  });

  const ordered = readingOrder(pieces, rows);
  diagnostics.push(`最终切出 ${ordered.length} 张贴纸`);
  return { pieces: ordered, diagnostics };
}

/** 先分行、行内再排左右，容忍每行贴纸的高低错位 */
function readingOrder(pieces: StickerPiece[], rows: number): StickerPiece[] {
  if (!pieces.length) return [];
  const byY = [...pieces].sort((a, b) => a.centroid[1] - b.centroid[1]);
  const perRow = Math.max(1, Math.round(byY.length / Math.max(rows, 1)));
  const out: StickerPiece[] = [];
  for (let i = 0; i < byY.length; i += perRow) {
    const band = byY
      .slice(i, i + perRow)
      .sort((a, b) => a.centroid[0] - b.centroid[0]);
    out.push(...band);
  }
  out.forEach((p, i) => {
    p.index = i + 1;
  });
  return out;
}
