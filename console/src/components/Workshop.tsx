import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { ACTION_META, type Action, POLICY } from '@/lib/compliance/policy';
import {
  type JobResult,
  decodeImage,
  hasExif,
  renderPreview,
  runSheetJob,
  stripMetadata,
} from '@/lib/pipeline';
import { DEFAULT_SPEC, EXPRESSIONS_ZH } from '@/lib/print/spec';
import { type FC, useCallback, useMemo, useRef, useState } from 'react';

interface OriginalItem {
  name: string;
  url: string;
  w: number;
  h: number;
  exifStripped: boolean;
  blob: Blob;
}

function download(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/**
 * 本地只跑得动确定性规则，视觉审核永远处于"待复核"。
 * 两种"不可下单"必须分开说：本地就没过 vs 本地过了在等引擎复核，
 * 否则运营会把后者也当成失败去返工。
 */
const VerdictBanner: FC<{ verdict: Action; localBlocked: boolean }> = ({
  verdict,
  localBlocked,
}) => {
  const meta = localBlocked ? ACTION_META[verdict] : ACTION_META.mitigate;
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${meta.tone}`}>
      <span className="font-semibold">
        {localBlocked ? `裁决：${meta.label}` : '本地质检通过'}
      </span>
      <span className="ml-3 opacity-80">
        {localBlocked
          ? '本地确定性规则未过，需按下方结论处置后重跑，不可下单印刷'
          : '待引擎侧 VLM 视觉闸门复核通过后方可下单印刷'}
      </span>
    </div>
  );
};

export const Workshop: FC = () => {
  const [originals, setOriginals] = useState<OriginalItem[]>([]);
  const [sheetImg, setSheetImg] = useState<ImageData | null>(null);
  const [sheetName, setSheetName] = useState('');
  const [sheetPreview, setSheetPreview] = useState('');
  const [subject, setSubject] = useState('我家的橘色博美');
  const [jobId, setJobId] = useState(
    () => `SP-${Date.now().toString(36).toUpperCase().slice(-6)}`,
  );
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState('');
  const [pct, setPct] = useState(0);
  const [result, setResult] = useState<JobResult | null>(null);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const originalRef = useRef<HTMLInputElement>(null);
  const sheetRef = useRef<HTMLInputElement>(null);

  const spec = DEFAULT_SPEC;

  const onOriginals = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    setError('');
    const items: OriginalItem[] = [];
    for (const f of Array.from(files)) {
      try {
        const img = await decodeImage(f);
        // D3 strip_exif：重编码即剥离全部元数据，包括 GPS
        const had = await hasExif(f);
        const clean = await stripMetadata(img);
        items.push({
          name: f.name,
          url: URL.createObjectURL(clean),
          w: img.width,
          h: img.height,
          exifStripped: had,
          blob: clean,
        });
      } catch {
        setError(`无法解码 ${f.name}，请确认是 JPG / PNG / WebP`);
      }
    }
    setOriginals(prev => [...prev, ...items]);
  }, []);

  const loadSheet = useCallback(async (blob: Blob, name: string) => {
    setError('');
    try {
      const img = await decodeImage(blob);
      setSheetImg(img);
      setSheetName(`${name}（${img.width}×${img.height}）`);
      setSheetPreview(URL.createObjectURL(blob));
      setResult(null);
      setPreview('');
    } catch {
      setError('贴纸大图解码失败');
    }
  }, []);

  const loadSample = useCallback(async () => {
    const res = await fetch('/demo/sheet_sample.jpg');
    await loadSheet(await res.blob(), '示例·博美六宫格');
  }, [loadSheet]);

  const run = useCallback(async () => {
    if (!sheetImg) return;
    setBusy(true);
    setResult(null);
    setPreview('');
    setError('');
    try {
      // 让出主线程，进度条才画得出来
      await new Promise(r => setTimeout(r, 30));
      const r = await runSheetJob(sheetImg, {
        spec,
        jobId,
        subject,
        labels: EXPRESSIONS_ZH,
        onProgress: (s, p) => {
          setStage(s);
          setPct(p);
        },
      });
      setResult(r);
      setPreview(renderPreview(r, spec));
    } catch (e) {
      setError(`排版失败：${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }, [sheetImg, jobId, subject, spec]);

  const manifest = useMemo(() => {
    if (!result) return '';
    return JSON.stringify(
      {
        job_id: result.jobId,
        created_at: result.createdAt,
        policy_version: result.policyVersion,
        compliance_fingerprint: result.fingerprint,
        verdict: result.verdict,
        printable: result.printable,
        sheet_spec: { ...spec, unit: 'mm' },
        stickers: result.sheet?.placements.map(p => ({
          index: p.index,
          label: p.label,
          x_mm: +p.x.toFixed(2),
          y_mm: +p.y.toFixed(2),
          w_mm: +p.w.toFixed(2),
          h_mm: +p.h.toFixed(2),
          effective_dpi: +p.effectiveDpi.toFixed(1),
        })),
        qc: result.qc,
        findings: result.findings,
        originals: originals.map(o => ({
          name: o.name,
          px: [o.w, o.h],
          exif_stripped: o.exifStripped,
        })),
      },
      null,
      2,
    );
  }, [result, originals, spec]);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* ---------------- 输入 ---------------- */}
      <div className="space-y-5">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">① 原始照片</CardTitle>
            <CardDescription>
              随成品一并交付的原图。上传即自动重编码剥离 EXIF（策略 D3 ·
              自动处置），不保留地理位置与设备信息。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              ref={originalRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={e => onOriginals(e.target.files)}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => originalRef.current?.click()}
            >
              选择照片（可多张）
            </Button>
            {originals.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {originals.map(o => (
                  <div key={o.url} className="w-24">
                    <img
                      src={o.url}
                      alt={o.name}
                      className="h-24 w-24 rounded border border-slate-200 object-cover"
                    />
                    <p
                      className="mt-1 truncate text-[11px] text-slate-500"
                      title={o.name}
                    >
                      {o.w}×{o.h}
                    </p>
                    {o.exifStripped && (
                      <p className="text-[11px] text-sky-600">已剥离 EXIF</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">② 六宫格贴纸图</CardTitle>
            <CardDescription>
              2×3 贴纸大图。<strong>首选带真 alpha 的透明 PNG</strong>
              （ChatGPT 贴纸导出的通常就是）；拿不到 alpha 时，可退回纯品红{' '}
              <span className="font-mono text-fuchsia-600">#FF00FF</span>{' '}
              背景走色度键。操作台负责背景透明化、切分、排版与质检。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              ref={sheetRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={e =>
                e.target.files?.[0] &&
                loadSheet(e.target.files[0], e.target.files[0].name)
              }
            />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => sheetRef.current?.click()}
              >
                选择贴纸大图
              </Button>
              <Button variant="ghost" size="sm" onClick={loadSample}>
                载入示例
              </Button>
            </div>
            {sheetPreview && (
              <div className="flex gap-3">
                <img
                  src={sheetPreview}
                  alt="贴纸大图"
                  className="h-32 w-auto rounded border border-slate-200 bg-[repeating-conic-gradient(#f1f5f9_0_25%,#fff_0_50%)] bg-[length:16px_16px] object-contain"
                />
                <p className="text-xs text-slate-500">{sheetName}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">③ 作业参数</CardTitle>
            <CardDescription>
              主体描述会过闸 2 的关键词护栏；作业号与合规指纹会印在台纸页脚。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="subject" className="text-xs">
                  主体描述
                </Label>
                <Input
                  id="subject"
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="job" className="text-xs">
                  作业号
                </Label>
                <Input
                  id="job"
                  value={jobId}
                  onChange={e => setJobId(e.target.value)}
                />
              </div>
            </div>
            <Button
              className="w-full"
              disabled={!sheetImg || busy}
              onClick={run}
            >
              {busy ? `${stage} …` : '开始排版并质检'}
            </Button>
            {busy && <Progress value={pct} className="h-1.5" />}
            {error && <p className="text-xs text-rose-600">{error}</p>}
          </CardContent>
        </Card>
      </div>

      {/* ---------------- 输出 ---------------- */}
      <div className="space-y-5">
        {!result && (
          <Card className="flex h-full min-h-[360px] items-center justify-center border-dashed">
            <p className="px-8 text-center text-sm text-slate-400">
              左侧载入贴纸大图后点击「开始排版并质检」。
              <br />
              抠图、切分、刀版矢量化全部在你的浏览器内完成，图片不上传服务器。
            </p>
          </Card>
        )}

        {result && (
          <>
            <VerdictBanner
              verdict={result.verdict}
              localBlocked={result.findings.some(
                f => f.code !== 'VLM' && f.action !== 'pass',
              )}
            />

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">A5 台纸预览</CardTitle>
                <CardDescription>
                  蓝框 = 成品裁切线（外侧 3mm 出血），品红线 = CutContour
                  模切刀版（不印刷）
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {preview && (
                  <img
                    src={preview}
                    alt="A5 台纸预览"
                    className="mx-auto max-h-[480px] w-auto rounded border border-slate-200 shadow-sm"
                  />
                )}
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={!result.sheet}
                    onClick={() =>
                      result.sheet &&
                      download(
                        `${result.jobId}_sticker_sheet_A5.svg`,
                        new Blob([result.sheet.svg], { type: 'image/svg+xml' }),
                      )
                    }
                  >
                    下载 A5 印刷 SVG
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      download(
                        `${result.jobId}_manifest.json`,
                        new Blob([manifest], { type: 'application/json' }),
                      )
                    }
                  >
                    下载交付清单
                  </Button>
                  {originals.map((o, i) => (
                    <Button
                      key={o.url}
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        download(
                          `${result.jobId}_original_${String(i + 1).padStart(2, '0')}.png`,
                          o.blob,
                        )
                      }
                    >
                      下载原图 {i + 1}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">印刷质检</CardTitle>
                <CardDescription>
                  合规指纹{' '}
                  <span className="font-mono text-slate-700">
                    {result.fingerprint}
                  </span>{' '}
                  · 策略 {result.policyVersion}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <tbody>
                    {result.qc.map(q => (
                      <tr
                        key={q.key}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="py-2 pr-3 text-slate-600">{q.label}</td>
                        <td className="py-2 pr-3 font-mono text-slate-900">
                          {q.value}
                        </td>
                        <td className="py-2 text-right">
                          <Badge variant={q.ok ? 'secondary' : 'destructive'}>
                            {q.ok ? '通过' : '未过'}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ul className="mt-3 space-y-1 text-xs text-slate-400">
                  {result.diagnostics.map(d => (
                    <li key={d}>· {d}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">合规结论</CardTitle>
                <CardDescription>
                  依据策略 {POLICY.policy_version}；视觉类目由服务端引擎的 VLM
                  闸门判定
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {result.findings.map(f => (
                  <div
                    key={`${f.code}-${f.name}`}
                    className={`rounded border px-3 py-2 text-xs ${ACTION_META[f.action].tone}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        [{f.code}] {f.name}
                      </span>
                      <span className="shrink-0 opacity-70">
                        {ACTION_META[f.action].label} · {f.source}
                      </span>
                    </div>
                    <p className="mt-1 opacity-80">{f.detail}</p>
                  </div>
                ))}
              </CardContent>
            </Card>

            {result.pieces.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">切分结果</CardTitle>
                  <CardDescription>
                    按阅读顺序编号，每张已独立带透明通道
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                    {result.sheet?.pngDataUrls.map((u, i) => (
                      <a
                        key={u.slice(-24)}
                        href={u}
                        download={`${result.jobId}_sticker_${String(i + 1).padStart(2, '0')}.png`}
                        className="group"
                      >
                        <img
                          src={u}
                          alt={`贴纸 ${i + 1}`}
                          className="aspect-square w-full rounded border border-slate-200 bg-[repeating-conic-gradient(#f1f5f9_0_25%,#fff_0_50%)] bg-[length:12px_12px] object-contain p-1 transition group-hover:border-fuchsia-400"
                        />
                        <p className="mt-1 truncate text-center text-[11px] text-slate-500">
                          {EXPRESSIONS_ZH[i] ?? `贴纸 ${i + 1}`}
                        </p>
                      </a>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
};
