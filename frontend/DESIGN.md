---
name: 易占 · 白金版
description: 以传统术数典籍为规则底本的行动辅助工具，宣纸暖白 × 铂金丝绢 × 金箔点缀
colors:
  paper: "#F6F2E8"
  surface: "#FBF8F0"
  piao-1: "#F0F3F4"
  piao-2: "#D9E0E3"
  piao-3: "#A8B5BB"
  band: "#EFE8D9"
  band-deep: "#E6DDC9"
  silk-hi: "#EFECE4"
  silk-mid: "#DCD7CA"
  silk-lo: "#C6C0B0"
  plat-line: "rgba(107, 102, 88, 0.20)"
  plat-line-strong: "rgba(107, 102, 88, 0.38)"
  plat-sheen-lo: "#D8D3C6"
  plat-text: "#6E6A5F"
  gold: "#C9A75C"
  gold-deep: "#8F7433"
  gold-wash: "rgba(201, 167, 92, 0.10)"
  gold-wash-strong: "rgba(201, 167, 92, 0.20)"
  foil-1: "#F2E6C0"
  foil-2: "#D9BC79"
  foil-3: "#C9A75C"
  foil-4: "#8F7433"
  on-foil: "#FBF7EA"
  ink: "#211F1B"
  ink-2: "#55524A"
  ink-3: "#6E6A5F"
  control-border: "#8A8476"
  state-hover: "#F0EBDD"
  state-selected: "#F5EEDC"
  state-selected-text: "#7B632E"
  state-disabled: "#E5E9EB"
  state-disabled-text: "#6E6A5F"
  focus-ring: "#7B632E"
  error-text: "#874736"
  error-bg: "#FBF4F1"
  error-border: "#B07C6D"
  success-text: "#4C6056"
  success-bg: "#F0F3F2"
  success-border: "#9AA9A2"
  wx-jin: "#665F52"
  wx-mu: "#536252"
  wx-shui: "#506571"
  wx-huo: "#745E57"
  wx-tu: "#71624F"
typography:
  display:
    fontFamily: '"Noto Serif SC", "Source Han Serif SC", "Source Han Serif CN", "STSong", "STZhongsong", "SimSun", serif'
    fontSize: "clamp(28px, 3.6vw, 36px)"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: '"Noto Serif SC", "Source Han Serif SC", "Source Han Serif CN", "STSong", "SimSun", serif'
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.9
  label:
    fontFamily: '"Kaiti SC", "STKaiti", "KaiTi", "DFKai-SB", "Noto Serif SC", serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.8
rounded:
  sm: "2px"
  md: "4px"
  lg: "8px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "16px"
  "4": "24px"
  "5": "36px"
  "6": "72px"
  "7": "108px"
components:
  button-primary:
    backgroundColor: "{colors.state-selected}"
    textColor: "{colors.gold-deep}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
    height: "44px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
    height: "44px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
    height: "44px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
    height: "40px"
---

# Design System: 易占 · 白金版

## Overview

**Creative North Star: "丝绢书案"**

设计世界是「宣纸书案上的一册线装书」：暖白宣纸铺底，铂金丝绢与缥灰蓝作次级层次，金箔只在小面积点睛。整体是克制的新中式静奢——不在装饰上用力，而在纸面质感、发丝线、字距与留白上做功。颜色体系以暖白为底、墨色为字、金色为强调，缥灰蓝作信息条与页脚的辅助层。

**Key Characteristics:**
- 宣纸暖白底 + 纸纹噪点，替代旧版的科技网格
- 金箔渐变只用于极小面积（金印、句读点、动爻、选中态），稀缺即意义
- 层级靠发丝线与留白，几乎不用阴影
- 字体走系统栈（宋体/明体 + 楷体），无 CDN 依赖
- 五行语义色低饱和，仅用于数据标记，不抢主视觉

## Colors

暖白为主、缥灰蓝为辅、金色作小面积强调；语义色（成功/错误/五行）降饱和，只承担数据区分。

### Primary
- **金箔** (`#C9A75C` / `--gold`): 强调的唯一主色。用于选中态边框、句读印点、动爻金、导航激活下划线。
- **深金** (`#8F7433` / `--gold-deep`): 金箔的深色伴生，用于金箔元素上的文字、链接、节号徽标、焦点环。

### Secondary
- **缥灰蓝** (`#F0F3F4` / `#D9E0E3` / `#A8B5BB`，`--piao-1/2/3`): 信息条、引文底色、发丝线、次级边框的冷灰辅助层，与暖白底形成同温对比。

### Neutral
- **宣纸** (`#F6F2E8` / `--paper`): 页面底色。
- **新纸** (`#FBF8F0` / `--surface`): 卡片、输入、浮层表面。
- **墨** (`#211F1B` / `#55524A` / `#6E6A5F`，`--ink/ink-2/ink-3`): 三级文字色，从标题到辅助说明。
- **丝绢** (`#EFECE4` / `#DCD7CA` / `#C6C0B0`，`--silk-hi/mid/lo`): 滚动条与高光层次的暖灰过渡。

### Named Rules
**The Sparse-Gold Rule.** 金色 (`#C9A75C` / `#8F7433`) 只出现在需要读者注意的最小面积上——选中态、节点、动爻、句读。任何屏面上金色占比不超过约 10%，它的稀缺是它的意义。

## Typography

**Display Font:** Noto Serif SC（宋体/明体族，回退 STSong / STZhongsong / SimSun / serif）
**Body Font:** Noto Serif SC（同族，正文 17px / 1.9）
**Label Font:** Kaiti SC（楷体，回退 STKaiti / KaiTi / DFKai-SB）

**Character:** 宋体承载标题与正文的庄重，楷体承担标签、徽标、引文、眉批的手写感；二者并用是线装本「刻本 + 楷批」的字面层次。

### Hierarchy
- **Display** (600, clamp(28px, 3.6vw, 36px), 1.4): 卷名大标题、页面 h1。
- **Headline** (600, clamp(22px, 2.8vw, 28px), 1.4): 工具页 h2 小节标题。
- **Title** (700, 20px, 1.25): 入口卡标题、卡片主标题。
- **Body** (400, 17px, 1.9): 正文，行长约 65–75ch。
- **Label** (400, 16px, 1.8): 楷体标签、签筹、按钮、导航项；宽字距 0.04em–0.1em 是楷体标签的识别特征。

## Layout

版心两级：阅读/工具页 `max-width: 936px`，首页宽版心 `max-width: 1152px`，均居中。页容器左右留白 `24px`，顶部 `36px`、底部 `72px`（移动端收窄为 `16px`）。导航栏固定高度 `56px`（`--bar-h`）。间距以 4px 为基准的 4/8/16/24/36/72/108 档；36/72/108 为四九组合档，用于大区块分隔。栅格 4 列起步，入口卡与特征卡在窄屏折叠为 2 列、再折叠为 1 列。桌面导航品牌右置（`grid-column: 3`），移动端抽屉分组收纳。

## Elevation & Depth

以「发丝线分层」为主：层级靠 1px 边框（`--plat-line` / `--piao-2`）与留白区分，几乎不用投影。仅三级轻浮层用暖纸同温阴影（`--shadow-1/2/3`，色相偏暖 `rgba(60,54,40,…)`），用于浮层、hover 抬升、下拉菜单。卡片默认无投影，靠 1px 边框立起。

## Shapes

圆角克制：内层小元素（签、徽章）`2px`，控件/按钮/输入 `4px`，卡片 `8px`，胶囊 chip `999px`。边框以 1px 发丝线为主；彩色 `border-left` 一律 1px（用于信息条、引文、警示的语义侧边，不超过 1px）。金印是方形圆角小印（36px），非圆形。

## Components

### Buttons
- **Shape:** 圆角 4px，楷体，宽字距 0.1em。
- **Primary (`.btn` / `.btn-foil`):** 金wash底 `--state-selected` + 深金边框 `--gold-deep` + 深金字，padding 12px 24px，min-height 44px。
- **Hover / Active:** hover 金bright底 `--foil-1` + shadow-2 轻抬；active 下沉 1px。
- **Secondary (`.btn-outline` / `.btn-inkline` / `.btn-ghost`):** 透明底 + 1px `--control-border`，墨灰字，padding 10px 20px，min-height 44px；hover 缥灰底。

### Chips（签筹 / 五行签）
- **Style (`.slip` / `.chip`):** 新纸底 + 1px `--plat-line-strong` 边框，min-height 40px。
- **State:** 选中 `.active` 金wash底 + 深金边框 + 深金字 + 加粗；hover 缥灰底。
- **五行签 (`.wx-chip`):** 灰阶底 + 墨字 + 8px 色点（低饱和五行色），色点承担五行区分，不整片着色。

### Cards / Containers
- **Corner Style:** 8px 圆角（`--radius-lg`）。
- **Background:** `--surface` 新纸白。
- **Shadow Strategy:** 默认无投影，1px `--plat-line` 边框立起；hover 可抬升到 shadow-2。
- **Internal Padding:** 20px（入口卡）。

### Inputs / Fields
- **Style:** 新纸底 + 1px `--control-border`，圆角 4px，min-height 44px。
- **Focus:** 无 outline，改深金边框 `--focus-ring` + 3px 金wash光环 `--state-selected`。
- **Error / Disabled:** 错误 `--error-text/bg/border` 暖红组；禁用 `--state-disabled` 灰底。

### Navigation
- **Style:** 楷体 16px，sticky 顶栏 56px，新纸底 + 缥灰底边；品牌（金印「易」+「易占」+ slogan「观天机 · 断人事」）右置。
- **State:** 激活项深金字 + 金色下划线 scaleX(1)；hover 缥灰底 + 下划线 scaleX(0.4)。
- **Mobile:** 抽屉分组收纳，链接 min-height 44px，激活项深金 + 1px 金色左边线。

### Signature Component: 振荡阶梯（`yz-flow-step`）
- **Shape:** 纸白圆角卡片（8px），左侧 1px 竖线时间轴 + 每层一个 8px 金色圆点节点，节点落在竖线上。
- **Behavior:** 层级标签（驱动 L0 → 物理相 L1 → 生命相 L2 → 符号相 L3）自上而下，四张卡片等距排列，无重叠、无 sticky。

## Do's and Don'ts

### Do:
- **Do** 让层级靠 1px 发丝线与留白区分，不靠重投影。
- **Do** 用 `--gold` / `--gold-deep` 做小面积强调（选中态、节点、动爻、句读）。
- **Do** 楷体标签用宽字距（0.04em–0.1em）保持「刻本 + 楷批」的识别特征。
- **Do** 触控目标 ≥44px，所有交互元素保留键盘焦点与可见焦点环。

### Don't:
- **Don't** 在卡片、列表项、警示框、callout 上使用超过 1px 的彩色 `border-left`（发丝线纪律）。
- **Don't** 大面积使用金色或把金色当背景色铺陈——金是句读，不是底漆。
- **Don't** 引入冷灰阴影替代暖纸同温阴影（阴影色相必须与纸底同温，`rgba(60,54,40,…)`）。
- **Don't** 给五行语义色（金木水火土）作大面积底色，它们只用于数据标记的色点与文字区分。
- **Don't** 动效使用空间位移的循环动画；尊重 `prefers-reduced-motion`，减少动态时只保留状态反馈。
