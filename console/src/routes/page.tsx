import { ConsoleHeader } from '@/components/ConsoleHeader';
import { DemoGallery } from '@/components/DemoGallery';
import { PolicyBoard } from '@/components/PolicyBoard';
import { SpecBoard } from '@/components/SpecBoard';
import { Workshop } from '@/components/Workshop';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function Page() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <ConsoleHeader />
      <main className="mx-auto max-w-6xl px-6 py-6">
        <Tabs defaultValue="demo">
          <TabsList className="mb-5">
            <TabsTrigger value="demo">成品样例</TabsTrigger>
            <TabsTrigger value="workshop">排版台</TabsTrigger>
            <TabsTrigger value="policy">合规策略</TabsTrigger>
            <TabsTrigger value="spec">规格与引擎</TabsTrigger>
          </TabsList>
          <TabsContent value="demo">
            <DemoGallery />
          </TabsContent>
          <TabsContent value="workshop">
            <Workshop />
          </TabsContent>
          <TabsContent value="policy">
            <PolicyBoard />
          </TabsContent>
          <TabsContent value="spec">
            <SpecBoard />
          </TabsContent>
        </Tabs>
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-5 text-xs leading-relaxed text-slate-400">
          StickerPress · 图片处理全部在浏览器本地完成，不上传服务器；含 AI
          生成与视觉审核的完整链路由引擎侧 CLI
          执行。实体印刷品不可召回，任何未过闸的作业都不会产出可下单文件。
        </div>
      </footer>
    </div>
  );
}
