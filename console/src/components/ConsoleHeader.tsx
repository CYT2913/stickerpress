import { POLICY } from '@/lib/compliance/policy';
import type { FC } from 'react';

export const ConsoleHeader: FC = () => (
  <header className="border-b border-slate-200 bg-white">
    <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-6 py-7">
      <div>
        <div className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-lg text-white"
            style={{
              background: 'linear-gradient(135deg,#FF00FF 0%,#7C3AED 100%)',
            }}
          >
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <title>StickerPress</title>
              <path
                d="M4 4h11l5 5v11a0 0 0 0 1 0 0H4z"
                strokeLinejoin="round"
              />
              <path d="M15 4v5h5" strokeLinejoin="round" />
            </svg>
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            StickerPress
          </h1>
          <span className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-500">
            A5 模切贴纸生产操作台
          </span>
        </div>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">
          把一张照片变成印厂能直接开工的 A5 台纸：148 × 210 mm 自包含 SVG、6
          张内嵌贴纸位图、6 条闭合矢量刀版（CutContour 专色 0.25 pt）+
          可回溯的合规指纹。内容安全由三道闸把守，策略与代码分离。
        </p>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 font-medium text-emerald-700">
          策略 {POLICY.policy_version}
        </span>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">
          fail-mode: {POLICY.fail_mode}
        </span>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">
          owner: {POLICY.owner}
        </span>
      </div>
    </div>
  </header>
);
