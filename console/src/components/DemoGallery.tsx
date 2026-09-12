import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { EXPRESSIONS_ZH } from '@/lib/print/spec';
import type { FC } from 'react';

/** 真实跑通的作业 DEMO-DOG，由引擎 CLI 端到端产出 */
const DEMO = {
  jobId: 'DEMO-DOG',
  fingerprint: 'F5B47CFA',
  policy: '2026.09-r2',
  style: '日系 Q 版',
  subject: '一只橘色的博美犬',
  verdict: 'pass',
  minDpi: '399.7 dpi',
  knifeGap: '10.8 mm',
  count: 6,
};

const STEPS = [
  {
    k: '入料',
    d: '原始照片过闸 1：格式 / 尺寸 / 分辨率 + EXIF 剥离 + 视觉审核',
  },
  { k: '生成', d: '注入风格与合规护栏，生成 2×3 六宫格贴纸（透明底优先）' },
  {
    k: '透明化',
    d: '自带 alpha 则直通；否则色度键 + 边缘连通性约束 + 溢色抑制',
  },
  {
    k: '切分',
    d: 'alpha 连通域分析，形态学闭运算并回飘散元素，按阅读顺序编号',
  },
  {
    k: '刀版',
    d: '填洞 → 外扩白边 → 平滑 → Moore 追踪 → RDP → 贝塞尔闭合路径',
  },
  { k: '排版', d: 'A5 + 3mm 出血，2×3 格位，CutContour 专色层，四角裁切标记' },
  { k: '出料', d: '闸 3 质检与视觉复核，写入合规指纹与审计日志' },
];

export const DemoGallery: FC = () => (
  <div className="space-y-5">
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">
              端到端样例作业 · {DEMO.jobId}
            </CardTitle>
            <CardDescription>
              由引擎 CLI 实跑产出：一张宠物照片 → 6 张贴纸 → A5 印刷
              SVG，未做任何人工修图
            </CardDescription>
          </div>
          <Badge className="bg-emerald-600 hover:bg-emerald-600">
            裁决 {DEMO.verdict} · 可下单
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 md:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-3">
          <figure>
            <img
              src="/demo/original_01.jpg"
              alt="输入原图"
              className="w-full rounded-lg border border-slate-200 object-cover"
            />
            <figcaption className="mt-1.5 text-xs text-slate-500">
              输入：一张照片
            </figcaption>
          </figure>
          <dl className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
            {[
              ['风格 SKU', DEMO.style],
              ['主体描述', DEMO.subject],
              ['贴纸数', `${DEMO.count} 张`],
              ['最低有效分辨率', DEMO.minDpi],
              ['刀版最小净距', DEMO.knifeGap],
              ['合规指纹', DEMO.fingerprint],
              ['策略版本', DEMO.policy],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 py-1">
                <dt className="text-slate-500">{k}</dt>
                <dd className="font-mono text-slate-800">{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="space-y-3">
          <figure>
            <img
              src="/demo/preview.jpg"
              alt="A5 台纸预览"
              className="mx-auto max-h-[520px] w-auto rounded-lg border border-slate-200 shadow-sm"
            />
            <figcaption className="mt-1.5 text-center text-xs text-slate-500">
              输出：A5 台纸（蓝框为成品裁切线，品红线为模切刀版）
            </figcaption>
          </figure>
          <div className="flex flex-wrap justify-center gap-2">
            <Button asChild size="sm">
              <a
                href="/demo/sticker_sheet_A5.svg"
                download="DEMO-DOG_sticker_sheet_A5.svg"
              >
                下载 A5 印刷 SVG
              </a>
            </Button>
            <Button asChild size="sm" variant="outline">
              <a
                href="/demo/original_01.jpg"
                download="DEMO-DOG_original_01.jpg"
              >
                下载原图
              </a>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <a
                href="/demo/sticker_sheet_A5.svg"
                target="_blank"
                rel="noreferrer"
              >
                在新窗口打开 SVG
              </a>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">6 张贴纸</CardTitle>
        <CardDescription>
          一套贴纸的情绪脚本固定为 6 种，避免模型生成重复表情
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {EXPRESSIONS_ZH.map((label, i) => (
            <figure key={label}>
              <img
                src={`/demo/stickers/sticker_0${i + 1}_thumb.png`}
                alt={label}
                className="aspect-square w-full rounded-lg border border-slate-200 bg-[repeating-conic-gradient(#f1f5f9_0_25%,#fff_0_50%)] bg-[length:12px_12px] object-contain p-1"
              />
              <figcaption className="mt-1 text-center text-[11px] text-slate-500">
                {label}
              </figcaption>
            </figure>
          ))}
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">流水线</CardTitle>
        <CardDescription>
          照片进、印刷文件出，中间七步全部可审计
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-2 md:grid-cols-2">
          {STEPS.map((s, i) => (
            <li
              key={s.k}
              className="flex gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
            >
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[11px] font-medium text-white">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-medium text-slate-800">{s.k}</p>
                <p className="text-xs leading-relaxed text-slate-500">{s.d}</p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  </div>
);
