// 单文件离线 HTML —— 第二步：用真实浏览器渲染图（mermaid 在 Node 里没有 DOM，会出不了图）
// =====================================================================================
// 前置：先跑 `python tools/build_doc_html.py` 生成骨架（图位置留 `<!--MMD:n-->` 占位）。
// 本程序：把骨架里的 mermaid 源码逐张 render 成 SVG，替换占位符，写出最终 HTML。
//
// 调用（Windows PowerShell；Tabbit 浏览器需在运行）：
//   $cli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
//   cmd.exe /d /c "`"$cli`" nodejs --task bagua-html --request-id build --timeout-ms 150000 < tools\build_doc_html.js"
//
// 说明：本程序运行在浏览器自带的 Node 环境里，可用 node:fs 直接读写文件。
// 之所以不把 mermaid 内联进 HTML，是因为预渲染成 SVG 后：离线可看、无需 JS、
// 打印正常、体积更小（约 200KB 而不是 3MB）。

const SKELETON = 'D:/Temp/User/_doc_skeleton.html';
const OUT_HTML = 'D:/Web/bagua/backend/docs/产品流程总图（对外·大师版）.html';
// 需要浏览器里加载过 mermaid 的宿主页（只含一个 CDN script 标签）
const HOST = 'file:///D:/Temp/User/_mmd_host.html';

const fs = await import('node:fs/promises');

await page.goto(HOST, { waitUntil: 'load', timeout: 45000 });
await page.waitForFunction(() => window.__ready === true && !!window.mermaid, null, {
  timeout: 60000,
  polling: 'raf',
});

const skel = await fs.readFile(SKELETON, 'utf8');
const m = skel.match(/<script type="application\/json" id="mmd-src">([\s\S]*?)<\/script>/);
if (!m) {
  throw new Error('骨架里找不到 mmd-src（先跑 build_doc_html.py）');
}
const src = JSON.parse(m[1]);

const svgs = [];
for (let i = 0; i < src.length; i++) {
  const one = await page.evaluate(async (arg) => {
    const r = await window.mermaid.render('doc' + arg.i, arg.code);
    return r.svg;
  }, { i: i, code: src[i] });
  if (!one || one.length < 500) {
    throw new Error('第 ' + (i + 1) + ' 张图渲染失败');
  }
  svgs.push(one);
}

let out = skel;
for (let i = 0; i < svgs.length; i++) {
  const marker = '<!--MMD:' + (i + 1) + '-->';
  if (out.indexOf(marker) < 0) {
    throw new Error('占位符缺失：' + marker);
  }
  // 用函数式替换：SVG 里可能含 $ 系列字符，字符串替换会被当成替换模式
  out = out.replace(marker, () => svgs[i]);
}

await fs.writeFile(OUT_HTML, out, 'utf8');

return {
  diagrams: svgs.length,
  svgKB: svgs.map((s) => Math.round(s.length / 1024)),
  totalKB: Math.round(out.length / 1024),
  leftoverMarkers: (out.match(/<!--MMD:/g) || []).length,
  externalRefs: (out.match(/<script src=|<link /g) || []).length,
  outPath: OUT_HTML,
};
