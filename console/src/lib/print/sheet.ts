/**
 * A5 印刷级 SVG 排版引擎（浏览器版，与 Python 引擎 layout/a5_sheet.py 同规格）。
 *
 * 产出的不是"把 PNG 塞进 SVG"，而是印厂可以直接开工的文件：
 *   canvas   148×210mm A5 成品（kiss-cut 台纸默认无出血），viewBox 以毫米为用户单位
 *   artwork    图层：6 张贴纸位图（base64 内嵌，无外链依赖）
 *   CutContour 图层：6 条闭合矢量刀版路径，只描边不填充，走模切机
 *   marks      图层：四角裁切标记
 *   trace      图层：作业号 / 合规指纹 / 策略版本
 *   guides     图层：安全区参考线，默认隐藏
 */

import {
  type Point,
  alphaToCutPath,
  minDistanceBetween,
  toBezierPath,
  transformPoints,
} from '../imaging/contour';
import type { StickerPiece } from '../imaging/segment';
import {
  FOOTER_BAND_MM,
  type SheetSpec,
  canvasH,
  canvasW,
  cellBoxes,
  slots,
} from './spec';

export const CUT_STROKE = '#FF00FF';
// 印厂约定刀线 0.25 pt；本文件用户单位是 mm，必须换算。
// 直接写 0.25 会得到 0.71 pt —— 2.8 倍过粗。
export const PT_TO_MM = 25.4 / 72;
export const CUT_STROKE_PT = 0.25;
export const CUT_STROKE_W = Number((CUT_STROKE_PT * PT_TO_MM).toFixed(4)); // ≈ 0.0882 mm
export const CELL_PAD_MM = 1.6; // 格位内缩，防止相邻刀版贴太近
export const TARGET_DPI_CAP = 400; // 位图重采样上限，控体积同时远高于 300dpi

export interface Placement {
  index: number;
  x: number;
  y: number;
  w: number;
  h: number;
  srcPx: [number, number];
  effectiveDpi: number;
  cutPoints: Point[];
  cutPathD: string;
  areaRatio: number;
  label: string;
}

export interface SheetBuildResult {
  svg: string;
  placements: Placement[];
  minKnifeGapMm: number;
  minEffectiveDpi: number;
  pngDataUrls: string[];
}

function esc(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 等比缩放贴纸到格位内 */
function fit(
  cell: [number, number, number, number],
  iw: number,
  ih: number,
  pad: number,
) {
  const [cx, cy, cw, ch] = cell;
  const s = Math.min((cw - 2 * pad) / iw, (ch - 2 * pad) / ih);
  const w = iw * s;
  const h = ih * s;
  return { x: cx + (cw - w) / 2, y: cy + (ch - h) / 2, w, h };
}

function toCanvas(img: ImageData): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = img.width;
  c.height = img.height;
  (c.getContext('2d') as CanvasRenderingContext2D).putImageData(img, 0, 0);
  return c;
}

/** LANCZOS 在浏览器里不可得，用 canvas 高质量重采样代替 */
function resample(img: ImageData, targetW: number): ImageData {
  if (img.width <= targetW || targetW < 32) return img;
  const ratio = targetW / img.width;
  const th = Math.max(1, Math.round(img.height * ratio));
  const dst = document.createElement('canvas');
  dst.width = targetW;
  dst.height = th;
  const ctx = dst.getContext('2d') as CanvasRenderingContext2D;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(toCanvas(img), 0, 0, targetW, th);
  return ctx.getImageData(0, 0, targetW, th);
}

export function buildSheetSvg(
  pieces: StickerPiece[],
  spec: SheetSpec,
  meta: {
    jobId?: string;
    fingerprint?: string;
    policyVersion?: string;
    title?: string;
    brand?: string;
    labels?: string[];
    cutOffsetPx?: number;
  } = {},
): SheetBuildResult {
  const cells = cellBoxes(spec);
  const n = Math.min(pieces.length, slots(spec));
  const placements: Placement[] = [];
  const pngDataUrls: string[] = [];

  for (let i = 0; i < n; i++) {
    const cell = cells[i];
    let im = pieces[i].image;
    const box = fit(cell, im.width, im.height, CELL_PAD_MM);

    const maxPxW = Math.round((box.w / 25.4) * TARGET_DPI_CAP);
    im = resample(im, maxPxW);

    const alpha = new Uint8Array(im.width * im.height);
    for (let k = 0; k < alpha.length; k++) alpha[k] = im.data[k * 4 + 3];

    const { points } = alphaToCutPath(alpha, im.width, im.height, {
      offsetPx: meta.cutOffsetPx ?? 0,
      simplifyPx: Math.max(1, im.width / 500),
      resamplePx: Math.max(4, im.width / 110),
      smoothR: Math.max(1, Math.round(im.width / 400)),
    });

    const scale = box.w / im.width; // mm per px
    const ptsMm = transformPoints(points, scale, box.x, box.y);

    placements.push({
      index: i + 1,
      x: box.x,
      y: box.y,
      w: box.w,
      h: box.h,
      srcPx: [im.width, im.height],
      effectiveDpi: box.w > 0 ? im.width / (box.w / 25.4) : 0,
      cutPoints: ptsMm,
      cutPathD: toBezierPath(ptsMm),
      areaRatio: (box.w * box.h) / (cell[2] * cell[3]),
      label: meta.labels?.[i] ?? `贴纸 ${i + 1}`,
    });
    pngDataUrls.push(toCanvas(im).toDataURL('image/png'));
  }

  let gap = Number.POSITIVE_INFINITY;
  for (let a = 0; a < placements.length; a++)
    for (let b = a + 1; b < placements.length; b++)
      gap = Math.min(
        gap,
        minDistanceBetween(placements[a].cutPoints, placements[b].cutPoints),
      );
  if (!Number.isFinite(gap)) gap = 0;

  const minDpi = placements.length
    ? Math.min(...placements.map(p => p.effectiveDpi))
    : 0;

  return {
    svg: renderSvg(spec, placements, pngDataUrls, meta),
    placements,
    minKnifeGapMm: gap,
    minEffectiveDpi: minDpi,
    pngDataUrls,
  };
}

function renderSvg(
  spec: SheetSpec,
  placements: Placement[],
  pngs: string[],
  meta: {
    jobId?: string;
    fingerprint?: string;
    policyVersion?: string;
    title?: string;
    brand?: string;
  },
): string {
  const W = canvasW(spec);
  const H = canvasH(spec);
  const bl = spec.bleed;
  const brand = meta.brand ?? 'StickerPress';
  const jobId = meta.jobId ?? '';
  const fp = meta.fingerprint ?? '';
  const pv = meta.policyVersion ?? '';
  const now = new Date().toISOString().slice(0, 16).replace('T', ' ');
  const o: string[] = [];
  const a = (s: string) => o.push(s);

  a('<?xml version="1.0" encoding="UTF-8"?>');
  a(`<!-- ${brand} · A5 die-cut sticker sheet -->`);
  a(
    '<!-- 图层说明 / Layers: artwork=印刷图案, CutContour=模切刀版(专色, 只描边不印), marks=裁切标记, trace=溯源信息, guides=参考线(默认隐藏) -->',
  );
  a(
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="${W}mm" height="${H}mm" viewBox="0 0 ${W} ${H}" version="1.1">`,
  );
  a(`  <title>${esc(meta.title ?? 'StickerPress A5 贴纸台纸')}</title>`);
  a(
    `  <desc>A5 ${spec.pageW}x${spec.pageH}mm + ${bl}mm bleed · ${placements.length} die-cut stickers · job=${esc(jobId)} · compliance=${esc(fp)} · policy=${esc(pv)}</desc>`,
  );
  a('  <metadata>');
  a(
    '    <cutcontour xmlns="urn:stickerpress:print" spot-color-name="CutContour" usage="die-cut" printed="false" unit="mm"/>',
  );
  a('  </metadata>');

  a(
    '  <g id="substrate" inkscape:groupmode="layer" inkscape:label="substrate">',
  );
  a(`    <rect x="0" y="0" width="${W}" height="${H}" fill="#FFFFFF"/>`);
  a('  </g>');

  a('  <g id="artwork" inkscape:groupmode="layer" inkscape:label="artwork">');
  placements.forEach((p, i) => {
    const href = pngs[i];
    a(
      `    <image id="sticker-${p.index}" x="${p.x.toFixed(3)}" y="${p.y.toFixed(3)}" width="${p.w.toFixed(3)}" height="${p.h.toFixed(3)}" preserveAspectRatio="none" image-rendering="optimizeQuality" xlink:href="${href}" href="${href}"/>`,
    );
  });
  a('  </g>');

  a(
    `  <g id="CutContour" inkscape:groupmode="layer" inkscape:label="CutContour" fill="none" stroke="${CUT_STROKE}" stroke-width="${CUT_STROKE_W}" stroke-linejoin="round" data-spot-color="CutContour" data-print="false">`,
  );
  for (const p of placements)
    if (p.cutPathD) a(`    <path id="cut-${p.index}" d="${p.cutPathD}"/>`);
  a('  </g>');

  // 裁切标记只在有出血时才画：标记本身要落在出血区里。
  // kiss-cut 台纸（bleed=0）的成品边就是纸边，画上去反而会被印出来。
  if (bl > 0) {
    a(
      '  <g id="marks" inkscape:groupmode="layer" inkscape:label="marks" stroke="#000000" stroke-width="0.2">',
    );
    const m = Math.min(4, bl);
    const tx0 = bl;
    const ty0 = bl;
    const tx1 = bl + spec.pageW;
    const ty1 = bl + spec.pageH;
    for (const [cx, cy, sx, sy] of [
      [tx0, ty0, -1, -1],
      [tx1, ty0, 1, -1],
      [tx0, ty1, -1, 1],
      [tx1, ty1, 1, 1],
    ]) {
      a(
        `    <line x1="${(cx + sx * 0.8).toFixed(2)}" y1="${cy.toFixed(2)}" x2="${(cx + sx * m).toFixed(2)}" y2="${cy.toFixed(2)}"/>`,
      );
      a(
        `    <line x1="${cx.toFixed(2)}" y1="${(cy + sy * 0.8).toFixed(2)}" x2="${cx.toFixed(2)}" y2="${(cy + sy * m).toFixed(2)}"/>`,
      );
    }
    a('  </g>');
  }

  const fy = bl + spec.pageH - spec.safeMargin - FOOTER_BAND_MM / 2 + 2.2;
  const left = bl + spec.safeMargin;
  const right = bl + spec.pageW - spec.safeMargin;
  a(
    '  <g id="trace" inkscape:groupmode="layer" inkscape:label="trace" font-family="Helvetica, Arial, sans-serif" fill="#9AA0A6">',
  );
  a(
    `    <line x1="${left}" y1="${(fy - 5.2).toFixed(2)}" x2="${right}" y2="${(fy - 5.2).toFixed(2)}" stroke="#E3E6EA" stroke-width="0.25"/>`,
  );
  a(
    `    <text x="${left}" y="${fy.toFixed(2)}" font-size="2.6" letter-spacing="0.08">${esc(brand)} · A5 ${spec.pageW}×${spec.pageH}mm · ${placements.length} stickers · ${now}</text>`,
  );
  a(
    `    <text x="${right}" y="${fy.toFixed(2)}" font-size="2.6" text-anchor="end" letter-spacing="0.08">JOB ${esc(jobId)} · CHK ${esc(fp)} · P${esc(pv)}</text>`,
  );
  a('  </g>');

  a(
    '  <g id="guides" inkscape:groupmode="layer" inkscape:label="guides" style="display:none" fill="none">',
  );
  a(
    `    <rect x="${bl}" y="${bl}" width="${spec.pageW}" height="${spec.pageH}" stroke="#00A3FF" stroke-width="0.2" stroke-dasharray="2 1.2"/>`,
  );
  a(
    `    <rect x="${bl + spec.safeMargin}" y="${bl + spec.safeMargin}" width="${spec.pageW - 2 * spec.safeMargin}" height="${spec.pageH - 2 * spec.safeMargin}" stroke="#22C55E" stroke-width="0.2" stroke-dasharray="1.2 1.2"/>`,
  );
  a('  </g>');

  a('</svg>');
  return o.join('\n');
}
