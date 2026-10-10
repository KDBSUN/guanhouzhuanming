# 易占 · 观候转明

以传统术数典籍为规则底本的行动辅助工具：**卦象给方向，八字画边界，每条判定都标注典籍出处、可展开原文核对。**

## 设计铁律

- **确定性归代码，语言归 AI，校准归人。** 排盘、体用、五行处方、应期、配卦等一切可计算的部分由代码确定；只有「解卦」「行动建议」两段自然语言交给大模型；判据与出处由人工逐字核回典籍。
- 每条判据都可回溯：见 `backend/docs/判据总表.md` 与 `backend/docs/产品流程总图（大师版）.html`。

## 功能

- **梅花易数**：时间占 / 字占 / 手动起卦（万物查卦 ＋ 形／色／性／位／体五轴自推）
- **纳甲六爻**
- **四柱八字**：命局校验、大运流年
- **AI 解卦**：确定性排盘与 LLM 解读分开，起卦不扣额度
- **应期之日**：程序确定性计算（非 AI 生成）
- 术语地图、记录（加密导出／导入）、反馈

## 目录结构

- `backend/` — FastAPI 服务：排盘引擎、命局校验、限流、邮件、外应配卦
- `frontend-baijin/` — React + Vite + TypeScript（白金版前端）
- `data/` — 六十四卦资料（排盘引擎读取）
- `backend/docs/` — 判据总表、产品流程总图

## 本地运行

### 后端

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env      # 填入 LLM / SMTP / ASR 密钥
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd frontend-baijin
npm install
npm run dev
```

## 测试与逐字回源

```bash
cd backend
python -m pytest tests/
```

「逐字回源」一类测试会把引文与典籍原文逐字比对，防止判据被顺手改写。

**书库不随仓库分发**（受版权保护）。它们按 `BOOKS_DIR` 环境变量 → 仓库根 `books/` → 仓库同级 `books/` 的顺序查找；找不到时这些测试**显式跳过**并说明找过哪些位置，不会静默通过：

```powershell
$env:BOOKS_DIR = "D:\某处\books"
```

## 许可

[GPL-3.0](LICENSE)。
