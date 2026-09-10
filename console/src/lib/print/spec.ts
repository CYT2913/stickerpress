/**
 * A5 印刷规格。与 Python 引擎 stickerpress/config.py 保持一致。
 * 所有长度单位统一为毫米；SVG 用户单位 = 1mm。
 */

export const A5_WIDTH_MM = 148;
export const A5_HEIGHT_MM = 210;
export const PRINT_DPI_MIN = 300;
export const FOOTER_BAND_MM = 10;
export const CHROMA_KEY_HEX = '#FF00FF';

export interface SheetSpec {
  pageW: number;
  pageH: number;
  /** kiss-cut 台纸默认 0：所有图形内缩在安全边距内，没有元素跨过成品边，因此不需要出血 */
  bleed: number;
  safeMargin: number;
  cols: number;
  rows: number;
  gutter: number;
  minKnifeGap: number;
  /** 单枚成品尺寸区间与硬下限（任一方向，mm） */
  pieceMin: number;
  pieceMax: number;
  pieceHardMin: number;
}

export const DEFAULT_SPEC: SheetSpec = {
  pageW: A5_WIDTH_MM,
  pageH: A5_HEIGHT_MM,
  bleed: 0,
  safeMargin: 10,
  cols: 2,
  rows: 3,
  gutter: 8,
  minKnifeGap: 8,
  pieceMin: 22,
  pieceMax: 62,
  pieceHardMin: 20,
};

export const canvasW = (s: SheetSpec) => s.pageW + 2 * s.bleed;
export const canvasH = (s: SheetSpec) => s.pageH + 2 * s.bleed;
export const slots = (s: SheetSpec) => s.cols * s.rows;

/** 6 个格位的 (x, y, w, h)，原点在画布左上角；底部预留 footer 追溯带 */
export function cellBoxes(s: SheetSpec): [number, number, number, number][] {
  const ox = s.bleed + s.safeMargin;
  const oy = s.bleed + s.safeMargin;
  const usableW = s.pageW - 2 * s.safeMargin;
  const usableH = s.pageH - 2 * s.safeMargin - FOOTER_BAND_MM;
  const cw = (usableW - (s.cols - 1) * s.gutter) / s.cols;
  const ch = (usableH - (s.rows - 1) * s.gutter) / s.rows;
  const out: [number, number, number, number][] = [];
  for (let r = 0; r < s.rows; r++) {
    for (let c = 0; c < s.cols; c++) {
      out.push([ox + c * (cw + s.gutter), oy + r * (ch + s.gutter), cw, ch]);
    }
  }
  return out;
}

export interface StyleSpec {
  key: string;
  nameZh: string;
  desc: string;
}

export const STYLE_LIBRARY: StyleSpec[] = [
  {
    key: 'kawaii',
    nameZh: '日系 Q 版',
    desc: '厚描边扁平矢量、高饱和、软赛璐璐上色',
  },
  {
    key: 'papercut',
    nameZh: '厚涂剪纸风',
    desc: '分层剪纸拼贴、复古暖色、强剪影',
  },
  {
    key: 'retro',
    nameZh: '复古印刷风',
    desc: '90 年代网点、四色限定、轻微套印偏移',
  },
  {
    key: 'watercolor',
    nameZh: '水彩绘本风',
    desc: '柔和水彩晕染、纸纹、细钢笔线',
  },
];

export const EXPRESSIONS_ZH = [
  '开心大笑',
  '困困睡觉',
  '震惊',
  '心动',
  '生气鼓包',
  '撒花庆祝',
];
