/**
 * 合规策略（浏览器侧）。
 *
 * policy.json 由 `stickerpress/tools/sync_policy.py` 从引擎的 policy.yaml 生成，
 * 保证操作台展示的策略与实际执行的策略永远是同一份，不会出现"页面说拦、引擎放行"。
 */

import raw from './policy.json';

export type Action = 'pass' | 'mitigate' | 'review' | 'block';
export type GateName = 'ingest' | 'generation' | 'egress';

export interface Category {
  code: string;
  key: string;
  name: string;
  group: string;
  severity: 'S0' | 'S1' | 'S2' | 'S3';
  action: Action;
  gates: GateName[];
  rationale?: string;
  judging_note?: string;
  remediation?: string;
  mitigation?: string;
}

export interface Policy {
  policy_version: string;
  updated_at: string;
  owner: string;
  fail_mode: Action;
  gates: Record<GateName, { enabled: boolean; vlm_review: boolean }>;
  categories: Category[];
  generation_guardrails: { positive: string[]; negative: string[] };
  keyword_blocklist: string[];
  quality_thresholds: {
    min_effective_dpi: number;
    min_sticker_area_ratio: number;
    max_sticker_area_ratio: number;
    min_knife_gap_mm: number;
    min_alpha_components: number;
    required_sticker_count: number;
  };
}

export const POLICY = raw as unknown as Policy;

export const ACTION_META: Record<Action, { label: string; tone: string }> = {
  pass: {
    label: '放行',
    tone: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  },
  mitigate: {
    label: '自动处置',
    tone: 'text-sky-700 bg-sky-50 border-sky-200',
  },
  review: {
    label: '转人工',
    tone: 'text-amber-700 bg-amber-50 border-amber-200',
  },
  block: { label: '拦截', tone: 'text-rose-700 bg-rose-50 border-rose-200' },
};

export const GATE_META: Record<
  GateName,
  { no: string; label: string; desc: string }
> = {
  ingest: { no: '闸 1', label: '入料', desc: '用户上传的原始照片' },
  generation: { no: '闸 2', label: '生成', desc: '主体文案与提示词护栏' },
  egress: { no: '闸 3', label: '出料', desc: '生成的贴纸与最终版面' },
};

export const SEVERITY_ORDER: Record<string, number> = {
  S0: 0,
  S1: 1,
  S2: 2,
  S3: 3,
};

/** 取最严处置：block > review > mitigate > pass */
export function worstAction(actions: Action[]): Action {
  const rank: Action[] = ['pass', 'mitigate', 'review', 'block'];
  return actions.reduce<Action>(
    (a, b) => (rank.indexOf(b) > rank.indexOf(a) ? b : a),
    'pass',
  );
}

export interface Finding {
  code: string;
  name: string;
  action: Action;
  detail: string;
  source: '确定性规则' | '视觉审核';
}

/** 闸 2：用户自定义文案的关键词兜底过滤（生产环境应接公司统一敏感词服务） */
export function screenText(text: string): Finding[] {
  const hits: Finding[] = [];
  const t = (text ?? '').trim();
  if (!t) return hits;
  for (const kw of POLICY.keyword_blocklist) {
    if (t.includes(kw)) {
      hits.push({
        code: 'KW',
        name: '敏感关键词',
        action: 'block',
        detail: `主体描述命中关键词「${kw}」`,
        source: '确定性规则',
      });
    }
  }
  if (
    /[A-Za-z]{3,}|[0-9]{3,}/.test(t) &&
    /(印上|写上|加上|带字|文字|slogan|logo)/i.test(t)
  ) {
    hits.push({
      code: 'E1',
      name: '贴纸上出现文字',
      action: 'review',
      detail: '文案要求在贴纸上添加可读文字，拼写错误将造成不可返工的印刷废品',
      source: '确定性规则',
    });
  }
  return hits;
}
