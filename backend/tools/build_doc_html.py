# -*- coding: utf-8 -*-
"""对外文档 → 单文件离线 HTML（截图内嵌成 base64，双击即开、可发微信）。

本版正文不再有流程图，所以**通常一步到位、不需要浏览器**：
    python tools/build_doc_html.py

若将来文档里又出现 ```mermaid 代码块，脚本会为每张图留下 `<!--MMD:n-->` 占位符，
此时才需要第二步：用真实浏览器把图渲染成 SVG 再回填（见 tools/build_doc_html.js，
mermaid 在 Node 里没有 DOM，出不了图）。

用法：
    python tools/build_doc_html.py                       # 默认：docs/产品流程总图（大师版）.md → 同名 .html
    python tools/build_doc_html.py --md X.md --out Y.html
    python tools/build_doc_html.py --no-embed            # 不内嵌图片，HTML 只引用相对路径（便于调试）
"""
import argparse
import base64
import html
import io
import json
import mimetypes
import re
from pathlib import Path

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
IMG_ONLY = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")

_BACKEND = Path(__file__).resolve().parents[1]
# 文档改过一次名（对外·大师版 → 大师版），默认路径跟着改——
# 不改的后果是脚本一直报 FileNotFoundError，而人只会以为"HTML 生成坏了"。
DEFAULT_MD = _BACKEND / "docs" / "产品流程总图（大师版）.md"

CSS = """
:root{--bg:#120d08;--panel:#1d1610;--gold:#d4a454;--gold-b:#f2d08c;--ink:#f4ead6;
--dim:#bfae92;--line:rgba(212,164,84,.26);--red:#d0705a;--green:#9db86a;
--serif:"STZhongsong","SimSun","Noto Serif SC","Songti SC",serif;
--sans:"Microsoft YaHei","PingFang SC","Noto Sans SC",system-ui,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
line-height:1.75;font-size:15.5px}
.wrap{max-width:1180px;margin:0 auto;padding:44px 26px 90px}
p,ul,ol,blockquote,h1.doc-title,h2,h3,hr,nav.toc,.hint,footer,.tw{max-width:840px;margin-left:auto;margin-right:auto}
h1.doc-title{font-family:var(--serif);font-size:2rem;letter-spacing:2px;text-align:center;
margin:0 auto 6px;color:var(--gold-b)}
h1.doc-title::after{content:"";display:block;width:70px;height:2px;margin:16px auto 0;
background:linear-gradient(90deg,transparent,var(--gold),transparent)}
h2{font-family:var(--serif);font-size:1.4rem;letter-spacing:1.5px;color:var(--gold-b);
margin:52px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}
h3{font-family:var(--serif);font-size:1.12rem;letter-spacing:1px;color:var(--gold);
margin:30px 0 10px}
p{margin:10px 0}
strong{color:var(--gold-b);font-weight:600}
code{font-family:Consolas,Menlo,monospace;font-size:.9em;background:rgba(212,164,84,.1);
border:1px solid var(--line);border-radius:5px;padding:1px 5px;color:var(--gold-b)}
a{color:var(--gold)}
hr{border:0;border-top:1px solid var(--line);margin:40px 0}
blockquote{margin:14px 0;padding:12px 16px;background:rgba(212,164,84,.07);
border-left:3px solid var(--gold);border-radius:0 8px 8px 0;color:var(--dim)}
.tw{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 12px;text-align:left;vertical-align:top;border-bottom:1px solid rgba(212,164,84,.14)}
th{background:rgba(212,164,84,.12);color:var(--gold-b);font-weight:600;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:rgba(212,164,84,.05)}
ul,ol{margin:12px 0;padding-left:26px}
li{margin:6px 0}
figure.shot{margin:24px auto 30px;padding:12px 12px 6px;background:#fbf8f2;border:1px solid #e6dcc6;
border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.35);max-width:1130px}
figure.shot img{display:block;width:100%;height:auto;border-radius:8px}
figure.shot figcaption{text-align:center;color:#8d7a58;font-size:12.5px;letter-spacing:.5px;margin-top:10px}
details.ascii{margin:14px 0 26px;border:1px dashed var(--line);border-radius:10px;
background:rgba(212,164,84,.04)}
details.ascii summary{cursor:pointer;padding:9px 14px;color:var(--dim);font-size:13.5px;user-select:none}
details.ascii pre{margin:0;padding:14px;overflow-x:auto;font-family:Consolas,"Courier New",monospace;
font-size:12.5px;white-space:pre;border-top:1px solid var(--line)}
nav.toc{margin:26px 0 8px;padding:18px 20px;background:rgba(212,164,84,.06);
border:1px solid var(--line);border-radius:14px;column-count:2;column-gap:28px}
nav.toc a{display:block;text-decoration:none;padding:3px 0;font-size:14px;color:var(--dim);break-inside:avoid}
nav.toc a:hover{color:var(--gold-b)}
nav.toc a.lvl3{padding-left:16px;font-size:13px;opacity:.85}
.hint{text-align:center;color:var(--dim);font-size:13px;margin:2px 0 24px}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);
font-size:12.5px;text-align:center;line-height:1.9}
@media (max-width:720px){nav.toc{column-count:1}.wrap{padding:26px 14px 60px}
h1.doc-title{font-size:1.5rem}h2{font-size:1.2rem}}
@media print{
 body{background:#fff;color:#1a1a1a}.wrap{max-width:none;padding:0}
 h1.doc-title,h2,h3,strong{color:#6b4a12}
 nav.toc,details.ascii{display:none}
 figure.shot{break-inside:avoid;background:#fff;border-color:#ddd;box-shadow:none}
 th{background:#f4efe4;color:#333}th,td{border-color:#ddd}
 blockquote{background:#faf7f0;border-left-color:#b28a3c}
}
"""


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def join_lines(buf):
    out = ""
    for k, ln in enumerate(buf):
        if k == 0:
            out = ln
        elif CJK.search(out[-1:]) and CJK.search(ln[:1]):
            out += ln
        else:
            out += " " + ln
    return out


def embed_image(path: Path, embed: bool, md_dir: Path) -> str:
    """图片 → 内嵌 data URI；--no-embed 时保留相对路径。"""
    if not embed:
        return path.relative_to(md_dir).as_posix()
    mime = mimetypes.guess_type(path.name)[0] or "image/webp"
    return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode("ascii"))


def tokenize(lines):
    blocks, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            lang = s[3:].strip()
            body, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            blocks.append(("mermaid" if lang == "mermaid" else "ascii", "\n".join(body)))
            continue
        if not s:
            i += 1
            continue
        if s == "---":
            blocks.append(("hr", ""))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
            continue
        if s.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                buf.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(("quote", join_lines(buf)))
            continue
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            items = []
            while i < len(lines):
                mm = re.match(r"^[-*]\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                items.append(mm.group(1).strip())
                i += 1
            blocks.append(("ul", items))
            continue
        m = re.match(r"^\d+\.\s+(.*)$", s)
        if m:
            items = []
            while i < len(lines):
                mm = re.match(r"^\d+\.\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                items.append(mm.group(1).strip())
                i += 1
            blocks.append(("ol", items))
            continue
        mi = IMG_ONLY.match(s)
        if mi:
            blocks.append(("img", mi.group(1), mi.group(2)))
            i += 1
            continue
        buf = []
        while i < len(lines):
            cur = lines[i].strip()
            if (not cur or cur == "---" or cur.startswith(("#", "|", "> ", "- ", "* ", "```", "!["))
                    or re.match(r"^\d+\.\s", cur)):
                break
            buf.append(cur)
            i += 1
        blocks.append(("p", join_lines(buf)))
    return blocks


def render(blocks, md_dir, embed):
    toc = [(b[1], b[2], "s%d" % n) for n, b in enumerate(
        [x for x in blocks if x[0] == "h" and x[1] in (2, 3)])]
    body, mmd, ti, missing = [], [], 0, []
    for b in blocks:
        kind = b[0]
        if kind == "h":
            lvl, txt = b[1], b[2]
            if lvl == 1:
                body.append('<h1 class="doc-title">%s</h1>' % inline(txt))
            else:
                anchor = ""
                if lvl in (2, 3):
                    anchor = ' id="%s"' % toc[ti][2]
                    ti += 1
                body.append("<h%d%s>%s</h%d>" % (lvl, anchor, inline(txt), lvl))
        elif kind == "p":
            body.append("<p>%s</p>" % inline(b[1]))
        elif kind == "img":
            alt, src = b[1], b[2]
            p = (md_dir / src).resolve()
            if not p.exists():
                missing.append(src)
                body.append('<p class="hint">［缺图：%s］</p>' % html.escape(src))
                continue
            body.append('<figure class="shot"><img src="%s" alt="%s">'
                        '<figcaption>%s</figcaption></figure>'
                        % (embed_image(p, embed, md_dir), html.escape(alt), html.escape(alt)))
        elif kind == "ul":
            body.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(x) for x in b[1]))
        elif kind == "ol":
            body.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(x) for x in b[1]))
        elif kind == "quote":
            body.append("<blockquote>%s</blockquote>" % inline(b[1]))
        elif kind == "hr":
            body.append("<hr>")
        elif kind == "table":
            rows = b[1]
            if not rows:
                continue
            head = "".join("<th>%s</th>" % inline(c) for c in rows[0])
            rest = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                            for r in rows[1:])
            body.append('<div class="tw"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                        % (head, rest))
        elif kind == "ascii":
            body.append('<details class="ascii"><summary>文字版</summary><pre>%s</pre></details>'
                        % html.escape(b[1]))
        elif kind == "mermaid":
            mmd.append(b[1])
            n = len(mmd)
            body.append('<figure class="shot"><div class="mmd" data-n="%d"><!--MMD:%d--></div>'
                        '<figcaption>图 %d</figcaption></figure>' % (n, n, n))
    toc_html = "".join('<a class="lvl%d" href="#%s">%s</a>'
                       % (lvl, aid, html.escape(txt, quote=False)) for lvl, txt, aid in toc)
    return body, mmd, toc_html, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(DEFAULT_MD))
    ap.add_argument("--out", default="")
    ap.add_argument("--no-embed", action="store_true", help="不内嵌图片")
    args = ap.parse_args()

    md_path = Path(args.md)
    out_path = Path(args.out) if args.out else md_path.with_suffix(".html")
    md_dir = md_path.parent

    blocks = tokenize(io.open(md_path, encoding="utf-8").read().split("\n"))
    body, mmd, toc_html, missing = render(blocks, md_dir, not args.no_embed)
    title = next((b[2] for b in blocks if b[0] == "h" and b[1] == 1), "文档")
    note = ("单文件版：截图已内嵌，无外部脚本，可离线打开／直接打印" if not args.no_embed
            else "调试版：图片按相对路径引用")

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<style>%s</style>
</head><body><div class="wrap">
<p class="hint">%s</p>
<nav class="toc">%s</nav>
%s
<footer>%s<br>本页为单文件离线版，由 Markdown 原稿生成（backend/tools/build_doc_html.py）。</footer>
</div>
%s</body></html>
""" % (html.escape(title), CSS, note, toc_html, "\n".join(body), html.escape(title),
       ('<script type="application/json" id="mmd-src">%s</script>' % json.dumps(mmd, ensure_ascii=False))
       if mmd else "")

    io.open(out_path, "w", encoding="utf-8", newline="\n").write(doc)
    print("图片 %d 张 ｜ mermaid %d 张 ｜ 目录 %d 项 ｜ 输出 %s（%.2f MB）"
          % (sum(1 for b in blocks if b[0] == "img"), len(mmd), toc_html.count("<a "),
             out_path, len(doc.encode("utf-8")) / 1048576))
    if missing:
        print("缺图（已在页面标注）：" + "、".join(missing))
    if mmd:
        print("注意：文档里仍有 mermaid 图，需用 tools/build_doc_html.js 在浏览器里回填 SVG。")


if __name__ == "__main__":
    main()
