import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  ACTION_META,
  type Action,
  GATE_META,
  type GateName,
  POLICY,
  SEVERITY_ORDER,
} from '@/lib/compliance/policy';
import redteam from '@/lib/compliance/redteam.json';
import { type FC, useMemo, useState } from 'react';

const GATES: GateName[] = ['ingest', 'generation', 'egress'];

interface RedteamCase {
  case: string;
  gate: string;
  title: string;
  expect: string[];
  actual: string;
  hits: string[];
  pass: boolean;
  seconds: number;
}

const RT = redteam as unknown as {
  policy_version: string;
  policy_fingerprint: string;
  passed: number;
  total: number;
  cases: RedteamCase[];
};

export const PolicyBoard: FC = () => {
  const [gate, setGate] = useState<GateName | 'all'>('all');

  const cats = useMemo(() => {
    const list =
      gate === 'all'
        ? POLICY.categories
        : POLICY.categories.filter(c => c.gates.includes(gate));
    return [...list].sort(
      (a, b) =>
        SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
        a.code.localeCompare(b.code),
    );
  }, [gate]);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">三道闸</CardTitle>
          <CardDescription>
            实体贴纸一旦印出就无法召回，所以拦截点必须前置到"下单之前"，而不是事后下架
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {GATES.map(g => {
            const cfg = POLICY.gates[g];
            const n = POLICY.categories.filter(c => c.gates.includes(g)).length;
            return (
              <div key={g} className="rounded-lg border border-slate-200 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-900">
                    {GATE_META[g].no} · {GATE_META[g].label}
                  </span>
                  <Badge variant={cfg.enabled ? 'secondary' : 'outline'}>
                    {cfg.enabled ? '启用' : '停用'}
                  </Badge>
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  {GATE_META[g].desc}
                </p>
                <p className="mt-3 text-xs text-slate-600">
                  覆盖 <span className="font-mono font-semibold">{n}</span>{' '}
                  个类目 · 视觉审核 {cfg.vlm_review ? '开' : '关'}
                </p>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">
                风险类目（{POLICY.categories.length}）
              </CardTitle>
              <CardDescription>
                策略与代码分离：增删类目、改处置动作只改
                policy.yaml，版本号会写进成品页脚
              </CardDescription>
            </div>
            <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-xs">
              {(['all', ...GATES] as const).map(g => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGate(g)}
                  className={`rounded px-2.5 py-1 transition ${
                    gate === g
                      ? 'bg-white font-medium text-slate-900 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  {g === 'all' ? '全部' : GATE_META[g].label}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {cats.map(c => (
            <div
              key={c.code}
              className="rounded-lg border border-slate-200 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-slate-400">
                  {c.code}
                </span>
                <span className="text-sm font-medium text-slate-900">
                  {c.name}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    c.severity === 'S0'
                      ? 'bg-rose-100 text-rose-700'
                      : c.severity === 'S1'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {c.severity}
                </span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[11px] ${ACTION_META[c.action as Action].tone}`}
                >
                  {ACTION_META[c.action as Action].label}
                </span>
                <span className="ml-auto text-[11px] text-slate-400">
                  {c.gates.map(g => GATE_META[g].label).join(' / ')}
                </span>
              </div>
              {c.rationale && (
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                  {c.rationale}
                </p>
              )}
              {c.judging_note && (
                <p className="mt-1 rounded bg-slate-50 px-2 py-1 text-[11px] leading-relaxed text-slate-500">
                  判定口径：{c.judging_note}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">红队回归</CardTitle>
              <CardDescription>
                策略指纹{' '}
                <span className="font-mono">{RT.policy_fingerprint}</span> ·
                每次改策略都要重跑
              </CardDescription>
            </div>
            <Badge
              className={
                RT.passed === RT.total
                  ? 'bg-emerald-600 hover:bg-emerald-600'
                  : 'bg-rose-600'
              }
            >
              {RT.passed} / {RT.total} 通过
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 pr-3 font-medium">用例</th>
                  <th className="py-2 pr-3 font-medium">场景</th>
                  <th className="py-2 pr-3 font-medium">期望</th>
                  <th className="py-2 pr-3 font-medium">实际</th>
                  <th className="py-2 pr-3 font-medium">命中</th>
                  <th className="py-2 font-medium">结果</th>
                </tr>
              </thead>
              <tbody>
                {RT.cases.map(c => (
                  <tr
                    key={c.case}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="py-2 pr-3 font-mono text-slate-500">
                      {c.case}
                    </td>
                    <td className="py-2 pr-3 text-slate-700">{c.title}</td>
                    <td className="py-2 pr-3 text-slate-500">
                      {c.expect.join(' / ')}
                    </td>
                    <td className="py-2 pr-3 font-medium text-slate-900">
                      {c.actual}
                    </td>
                    <td className="py-2 pr-3 text-slate-500">
                      {c.hits.join('、') || '—'}
                    </td>
                    <td className="py-2">
                      <Badge variant={c.pass ? 'secondary' : 'destructive'}>
                        {c.pass ? 'PASS' : 'FAIL'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
            其中 G1-BLOCK-IDCARD
            曾经是一个真实的静默放行故障：视觉审核工具的返回被包装成
            <span className="font-mono"> AimeToolResultText(result=…) </span>
            外壳，解析层没有解包，导致所有类目退化成"未覆盖"，仿证件样本被判
            pass。修复后补上了覆盖率兜底—— 审核结果覆盖不足 60% 直接抛错走
            fail-mode 转人工，而不是当作没有风险。
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">生成侧硬约束</CardTitle>
          <CardDescription>
            拼进每一次生成请求，防止模型自发越界（闸 2）
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium text-emerald-700">正向</p>
            <ul className="space-y-1">
              {POLICY.generation_guardrails.positive.map(g => (
                <li
                  key={g}
                  className="rounded bg-emerald-50 px-2 py-1 font-mono text-[11px] text-emerald-800"
                >
                  {g}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-2 text-xs font-medium text-rose-700">负向</p>
            <ul className="space-y-1">
              {POLICY.generation_guardrails.negative.map(g => (
                <li
                  key={g}
                  className="rounded bg-rose-50 px-2 py-1 font-mono text-[11px] text-rose-800"
                >
                  {g}
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
