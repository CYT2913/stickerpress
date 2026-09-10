import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { POLICY } from '@/lib/compliance/policy';
import {
  DEFAULT_SPEC,
  STYLE_LIBRARY,
  canvasH,
  canvasW,
  cellBoxes,
} from '@/lib/print/spec';
import type { FC } from 'react';

const s = DEFAULT_SPEC;
const cell = cellBoxes(s)[0];

const LAYERS = [
  ['substrate', '满版白底（A5 成品尺寸）'],
  ['artwork', '6 张贴纸位图，base64 内嵌，无外链依赖'],
  ['CutContour', '6 条闭合矢量刀版路径，专色只描边不印刷'],
  ['marks', '四角裁切标记，仅在设为出血版式时输出'],
  ['trace', '作业号 / 合规指纹 / 策略版本，实体成品可回溯'],
  ['guides', '安全区参考线，默认隐藏'],
];

export const SpecBoard: FC = () => (
  <div className="space-y-5">
    <div className="grid gap-5 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">版面</CardTitle>
          <CardDescription>单位统一为毫米，SVG 用户单位 = 1mm</CardDescription>
        </CardHeader>
        <CardContent>
          <svg
            viewBox={`0 0 ${canvasW(s)} ${canvasH(s)}`}
            className="mx-auto h-auto w-full max-w-[220px] rounded border border-slate-200"
            role="img"
            aria-label="A5 版面示意"
          >
            <title>A5 版面示意</title>
            <rect
              x="0"
              y="0"
              width={canvasW(s)}
              height={canvasH(s)}
              fill="#FDF2F8"
            />
            <rect
              x={s.bleed}
              y={s.bleed}
              width={s.pageW}
              height={s.pageH}
              fill="#fff"
              stroke="#00A3FF"
              strokeWidth="0.5"
              strokeDasharray="3 1.6"
            />
            {cellBoxes(s).map((c, i) => (
              <g key={`${c[0]}-${c[1]}`}>
                <rect
                  x={c[0]}
                  y={c[1]}
                  width={c[2]}
                  height={c[3]}
                  fill="#FCE7F3"
                  stroke="#FF00FF"
                  strokeWidth="0.4"
                />
                <text
                  x={c[0] + c[2] / 2}
                  y={c[1] + c[3] / 2 + 3}
                  textAnchor="middle"
                  fontSize="8"
                  fill="#DB2777"
                  fontFamily="Helvetica"
                >
                  {i + 1}
                </text>
              </g>
            ))}
            <line
              x1={s.bleed + s.safeMargin}
              y1={canvasH(s) - s.bleed - s.safeMargin - 4}
              x2={canvasW(s) - s.bleed - s.safeMargin}
              y2={canvasH(s) - s.bleed - s.safeMargin - 4}
              stroke="#CBD5E1"
              strokeWidth="0.4"
            />
            <text
              x={s.bleed + s.safeMargin}
              y={canvasH(s) - s.bleed - s.safeMargin}
              fontSize="4"
              fill="#94A3B8"
            >
              JOB · CHK · POLICY
            </text>
          </svg>
          <p className="mt-3 text-center text-[11px] text-slate-500">
            蓝虚线 = 成品裁切线，绿虚线 = 安全边距，品红框 = 贴纸格位
          </p>
        </CardContent>
      </Card>

      <div className="space-y-5">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">印刷规格</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {[
                ['成品尺寸', `${s.pageW} × ${s.pageH} mm（ISO A5）`],
                ['SVG 画布', `${canvasW(s)} × ${canvasH(s)} mm`],
                [
                  '出血',
                  s.bleed > 0
                    ? `${s.bleed} mm（四周）`
                    : '0 mm — kiss-cut 台纸无元素跨过成品边，不需要出血',
                ],
                ['安全边距', `${s.safeMargin} mm`],
                [
                  '版面栅格',
                  `${s.cols} 列 × ${s.rows} 行 = ${s.cols * s.rows} 张`,
                ],
                [
                  '单格尺寸',
                  `${cell[2].toFixed(1)} × ${cell[3].toFixed(1)} mm`,
                ],
                ['贴纸间距', `${s.gutter} mm`],
                ['刀版最小净距', `${s.minKnifeGap} mm`],
                [
                  '单枚尺寸',
                  `${s.pieceMin}–${s.pieceMax} mm（硬下限 ${s.pieceHardMin} mm）`,
                ],
                [
                  '分辨率门槛',
                  `${POLICY.quality_thresholds.min_effective_dpi} dpi`,
                ],
                ['模切专色', 'CutContour（#FF00FF，0.25 pt 描边，不印刷）'],
              ].map(([k, v]) => (
                <div
                  key={k}
                  className="flex justify-between gap-3 border-b border-slate-100 py-1.5"
                >
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="text-right font-mono text-xs text-slate-800">
                    {v}
                  </dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">SVG 图层</CardTitle>
            <CardDescription>
              印厂拿到文件后按图层分工，不需要额外沟通
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {LAYERS.map(([k, v]) => (
                <li key={k} className="flex gap-3">
                  <code className="w-24 shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700">
                    {k}
                  </code>
                  <span className="text-xs leading-5 text-slate-600">{v}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>

    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">风格 SKU</CardTitle>
        <CardDescription>
          商业化时这一层就是款式；每套固定 6 种情绪，避免表情重复
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STYLE_LIBRARY.map(st => (
          <div key={st.key} className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-medium text-slate-900">{st.nameZh}</p>
            <code className="text-[11px] text-slate-400">{st.key}</code>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
              {st.desc}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">引擎侧 CLI</CardTitle>
        <CardDescription>
          含 AI 生成与 VLM
          视觉审核的完整链路跑在引擎里；浏览器操作台只承担排版、质检与策略查阅
        </CardDescription>
      </CardHeader>
      <CardContent>
        <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-[12px] leading-relaxed text-slate-100">
          <code>{`# 一张照片 → A5 印刷台纸
python3 -m stickerpress.cli run photo.jpg \\
  --style kawaii \\
  --subject "一只橘色的博美犬" \\
  --resolution 4k \\
  --operator "chenyitong.ffhp" \\
  -o ./out --job-id DEMO-DOG

# 查看当前生效策略 / 风格库
python3 -m stickerpress.cli policy
python3 -m stickerpress.cli styles

# 红队回归（改完策略必跑）
python3 tools/redteam_suite.py`}</code>
        </pre>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          交付目录：<code className="text-slate-700">sticker_sheet_A5.svg</code>{' '}
          · <code className="text-slate-700">preview.png</code> ·{' '}
          <code className="text-slate-700">originals/</code> ·{' '}
          <code className="text-slate-700">stickers/</code> ·{' '}
          <code className="text-slate-700">audit.json</code> ·{' '}
          <code className="text-slate-700">manifest.json</code> ·{' '}
          <code className="text-slate-700">report.md</code>
        </p>
      </CardContent>
    </Card>
  </div>
);
