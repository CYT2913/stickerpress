#!/usr/bin/env node
/**
 * 把仓库根 assets/samples/ 里的印刷级示例台纸同步到操作台的静态目录。
 *
 * 为什么要有这个脚本：那份 SVG 内嵌了 6 张 400 dpi 位图，十几 MB。
 * 仓库里只保留一份真源（assets/samples/），不在 console 下再存一份副本，
 * 否则每次重新生成示例都会在 git 历史里多压十几 MB 死重量。
 *
 * 用法：node scripts/sync-samples.mjs   （或 pnpm run sync:samples）
 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..', '..');

const JOBS = [
  [
    'assets/samples/sample_a5_sheet.svg',
    'console/config/public/demo/sticker_sheet_A5.svg',
  ],
];

let missing = 0;
for (const [from, to] of JOBS) {
  const src = resolve(repoRoot, from);
  const dst = resolve(repoRoot, to);
  if (!existsSync(src)) {
    console.error(`[x] 缺少示例源文件：${from}`);
    missing += 1;
    continue;
  }
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(src, dst);
  console.log(`[ok] ${from} -> ${to}`);
}

if (missing > 0) {
  console.error(
    '\n示例资源不完整。示例台纸由引擎生成，见 docs/PRINT_SPEC.md。',
  );
  process.exit(1);
}
