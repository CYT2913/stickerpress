/**
 * 浏览器端排版流水线。
 *
 * 说明边界：AI 生成与 VLM 视觉审核跑在服务端引擎里，浏览器拿不到模型。
 * 所以操作台只承担"已有六宫格贴纸图 → 印刷级 A5 台纸"这一段，
 * 加上不依赖模型的确定性预检（格式 / 分辨率 / EXIF / 关键词 / 印刷质检）。
 * 凡是需要视觉审核的类目，一律标注为"需引擎复核"，绝不在页面上假装已通过。
 */

import {
  type Action,
  type Finding,
  POLICY,
  screenText,
  worstAction,
} from './compliance/policy';
import { chromaKey, hasUsableAlpha, transparentRatio } from './imaging/chroma';
import { type StickerPiece, splitSheet } from './imaging/segment';
import { type SheetBuildResult, buildSheetSvg } from './print/sheet';
import { type SheetSpec, canvasH, canvasW } from './print/spec';

export interface QcItem {
  key: string;
  label: string;
  value: string;
  ok: boolean;
  hint?: string;
}

export interface JobResult {
  jobId: string;
  fingerprint: string;
  policyVersion: string;
  verdict: Action;
  findings: Finding[];
  qc: QcItem[];
  pieces: StickerPiece[];
  sheet: SheetBuildResult | null;
  diagnostics: string[];
  /** 背景透明化方式：alpha 直通，或品红色度键兜底 */
  backgroundMode: 'alpha' | 'chroma';
  backgroundRatio: number;
  printable: boolean;
  createdAt: string;
}

/** 读文件为 ImageData */
export async function decodeImage(file: Blob): Promise<ImageData> {
  const bitmap = await createImageBitmap(file);
  const c = document.createElement('canvas');
  c.width = bitmap.width;
  c.height = bitmap.height;
  const ctx = c.getContext('2d', {
    willReadFrequently: true,
  }) as CanvasRenderingContext2D;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close?.();
  return ctx.getImageData(0, 0, c.width, c.height);
}

/** JPEG 里是否带 EXIF（含可能的 GPS）。命中后走 D3 mitigate：重编码剥离 */
export async function hasExif(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 64).arrayBuffer());
  if (head[0] !== 0xff || head[1] !== 0xd8) return false; // 非 JPEG
  for (let i = 2; i < head.length - 1; i++) {
    if (head[i] === 0xff && (head[i + 1] === 0xe1 || head[i + 1] === 0xe0))
      return true;
  }
  return false;
}

/** 重新编码 = 剥离所有元数据。对应策略 D3 的 strip_exif 处置 */
export async function stripMetadata(img: ImageData): Promise<Blob> {
  const c = document.createElement('canvas');
  c.width = img.width;
  c.height = img.height;
  (c.getContext('2d') as CanvasRenderingContext2D).putImageData(img, 0, 0);
  return await new Promise<Blob>(resolve =>
    c.toBlob(b => resolve(b as Blob), 'image/png'),
  );
}

/** 8 位十六进制合规指纹，会印在成品页脚，用于实体贴纸回溯 */
export async function fingerprint(parts: string[]): Promise<string> {
  const buf = new TextEncoder().encode(parts.join('|'));
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(digest).slice(0, 4))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
}

export interface RunOptions {
  spec: SheetSpec;
  jobId: string;
  subject?: string;
  operator?: string;
  labels?: string[];
  onProgress?: (stage: string, pct: number) => void;
}

/**
 * 输入一张六宫格贴纸大图（首选已带真 alpha 的透明 PNG，其次品红色度键背景），
 * 输出 A5 印刷级台纸 + 质检结论。
 */
export async function runSheetJob(
  sheetImage: ImageData,
  opts: RunOptions,
): Promise<JobResult> {
  const p = opts.onProgress ?? (() => undefined);
  const findings: Finding[] = [];
  const th = POLICY.quality_thresholds;

  p('闸 2 · 文案护栏', 8);
  findings.push(...screenText(opts.subject ?? ''));

  p('背景透明化', 22);
  let rgba = sheetImage;
  let bgRatio = 1;
  // 优先真 alpha：ChatGPT 等导出的贴纸 PNG 通常自带透明通道，
  // 直通比色度键干净（无溢色、无阈值损失）。拿不到 alpha 才走品红兜底。
  let bgMode: 'alpha' | 'chroma' = 'chroma';
  if (hasUsableAlpha(sheetImage)) {
    bgMode = 'alpha';
    bgRatio = transparentRatio(sheetImage);
  } else {
    const keyed = chromaKey(sheetImage);
    rgba = keyed.rgba;
    bgRatio = keyed.backgroundRatio;
  }

  p('切分 · 连通域分析', 48);
  const { pieces, diagnostics } = splitSheet(rgba, {
    expected: th.required_sticker_count,
  });

  p('排版 · A5 刀版', 68);
  const fp = await fingerprint([
    opts.jobId,
    String(sheetImage.width),
    String(sheetImage.height),
    opts.subject ?? '',
  ]);

  let sheet: SheetBuildResult | null = null;
  if (pieces.length > 0) {
    sheet = buildSheetSvg(pieces, opts.spec, {
      jobId: opts.jobId,
      fingerprint: fp,
      policyVersion: POLICY.policy_version,
      labels: opts.labels,
    });
  }

  p('闸 3 · 印刷质检', 88);
  const qc: QcItem[] = [];
  qc.push({
    key: 'count',
    label: '贴纸数量',
    value: `${pieces.length} / ${th.required_sticker_count}`,
    ok: pieces.length === th.required_sticker_count,
    hint: '缺一不排版：A5 版面固定 6 格，少一张会留白，多一张会挤压刀版间距',
  });
  qc.push({
    key: 'bg',
    label:
      bgMode === 'alpha'
        ? '透明背景占比（alpha 直通）'
        : '色度键背景占比（品红兜底）',
    value: `${(bgRatio * 100).toFixed(1)}%`,
    ok: bgRatio > 0.15,
    hint:
      bgMode === 'alpha'
        ? '输入自带 alpha，已跳过色度键；低于 15% 说明透明区域过少，可能是假透明'
        : '低于 15% 说明模型没画出纯品红底，抠图不可信',
  });
  if (sheet) {
    qc.push({
      key: 'dpi',
      label: '最低有效分辨率',
      value: `${sheet.minEffectiveDpi.toFixed(0)} dpi`,
      ok: sheet.minEffectiveDpi >= th.min_effective_dpi,
      hint: `商业印刷门槛 ${th.min_effective_dpi} dpi`,
    });
    qc.push({
      key: 'gap',
      label: '刀版最小净距',
      value: `${sheet.minKnifeGapMm.toFixed(1)} mm`,
      ok: sheet.minKnifeGapMm >= th.min_knife_gap_mm,
      hint: `低于 ${th.min_knife_gap_mm}mm 模切易连刀排废`,
    });
    const ratios = sheet.placements.map(x => x.areaRatio);
    const lo = Math.min(...ratios);
    const hi = Math.max(...ratios);
    qc.push({
      key: 'area',
      label: '格位占用率',
      value: `${(lo * 100).toFixed(0)}% ~ ${(hi * 100).toFixed(0)}%`,
      ok: lo >= th.min_sticker_area_ratio && hi <= th.max_sticker_area_ratio,
      hint: '过小说明抠图丢主体，过大说明贴边会被裁',
    });

    // 单枚成品尺寸：太小撕不动也贴不牢，太大就不是贴纸了
    const shortest = Math.min(...sheet.placements.map(p => Math.min(p.w, p.h)));
    const longest = Math.max(...sheet.placements.map(p => Math.max(p.w, p.h)));
    qc.push({
      key: 'size',
      label: '单枚贴纸尺寸',
      value: `${shortest.toFixed(0)} ~ ${longest.toFixed(0)} mm`,
      ok: shortest >= opts.spec.pieceHardMin && longest <= opts.spec.pieceMax,
      hint: `硬下限 ${opts.spec.pieceHardMin}mm，建议 ${opts.spec.pieceMin}–${opts.spec.pieceMax}mm`,
    });

    // 安全边距：任何刀线都不得进入距成品边 safeMargin 的范围
    const cw = canvasW(opts.spec);
    const ch = canvasH(opts.spec);
    const margin = Math.min(
      ...sheet.placements.map(p =>
        Math.min(p.x, p.y, cw - (p.x + p.w), ch - (p.y + p.h)),
      ),
    );
    qc.push({
      key: 'margin',
      label: '安全边距',
      value: `${margin.toFixed(1)} mm`,
      ok: margin >= opts.spec.safeMargin - 1e-6,
      hint: `门槛 ${opts.spec.safeMargin}mm，裁切误差会吃掉更靠边的图形`,
    });
  }

  for (const item of qc) {
    if (!item.ok) {
      findings.push({
        code: 'QC',
        name: `印刷质检未过：${item.label}`,
        action: 'review',
        detail: `${item.value}｜${item.hint ?? ''}`,
        source: '确定性规则',
      });
    }
  }

  // 浏览器跑不了视觉审核，必须显式声明，不能默认放行
  findings.push({
    code: 'VLM',
    name: '视觉内容审核未在本地执行',
    action: 'review',
    detail:
      '肖像 / IP / 违禁 / 证件 / 机读码等类目需由服务端引擎的 VLM 闸门判定，本地排版台不作结论',
    source: '视觉审核',
  });

  const verdict = worstAction(findings.map(f => f.action));
  p('完成', 100);

  return {
    jobId: opts.jobId,
    fingerprint: fp,
    policyVersion: POLICY.policy_version,
    verdict,
    findings,
    qc,
    pieces,
    sheet,
    diagnostics,
    backgroundMode: bgMode,
    backgroundRatio: bgRatio,
    printable: verdict !== 'block' && verdict !== 'review',
    createdAt: new Date().toISOString(),
  };
}

/** 台纸预览（不参与印刷，仅供下单前确认） */
export function renderPreview(
  result: JobResult,
  spec: SheetSpec,
  dpi = 120,
): string {
  const k = dpi / 25.4;
  const W = Math.round(canvasW(spec) * k);
  const H = Math.round(canvasH(spec) * k);
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  const ctx = c.getContext('2d') as CanvasRenderingContext2D;
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, W, H);
  if (!result.sheet) return c.toDataURL('image/png');

  result.sheet.placements.forEach((pl, i) => {
    const im = result.pieces[i].image;
    const tmp = document.createElement('canvas');
    tmp.width = im.width;
    tmp.height = im.height;
    (tmp.getContext('2d') as CanvasRenderingContext2D).putImageData(im, 0, 0);
    ctx.drawImage(tmp, pl.x * k, pl.y * k, pl.w * k, pl.h * k);
  });

  ctx.strokeStyle = '#FF00FF';
  ctx.lineWidth = Math.max(1, dpi / 150);
  for (const pl of result.sheet.placements) {
    if (pl.cutPoints.length < 3) continue;
    ctx.beginPath();
    pl.cutPoints.forEach(([x, y], i) =>
      i ? ctx.lineTo(x * k, y * k) : ctx.moveTo(x * k, y * k),
    );
    ctx.closePath();
    ctx.stroke();
  }

  ctx.strokeStyle = '#00A3FF';
  ctx.lineWidth = Math.max(1, dpi / 200);
  ctx.strokeRect(
    spec.bleed * k,
    spec.bleed * k,
    spec.pageW * k,
    spec.pageH * k,
  );
  return c.toDataURL('image/png');
}
