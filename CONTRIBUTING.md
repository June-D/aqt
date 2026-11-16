# Contributing

感谢参与 AQT。提交前请先确认改动范围清晰、可复现，并尽量附带测试。

## 开发环境

```bash
cp .env.example .env
./scripts/run_dev.sh --dev-ui
```

- 后端：Python 3.10+，FastAPI + SQLite
- 前端：Node 18+，React + Vite
- 首次运行会创建 `data/trade.db`

## 提交前检查

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

## 约定

- 不要提交 `.env`、`data/`、`frontend/dist/`、日志或任何密钥。
- 涉及风控、下单、网关、鉴权的改动必须附带测试。
- 前端改动请先阅读 [DESIGN.md](DESIGN.md)，保持现有「Ledger Desk」设计语言。
- Python 使用 4 空格缩进；前端使用 2 空格，沿用现有 ESLint / 代码风格。
- 提交信息建议使用 Conventional Commits：`feat: ...`、`fix: ...`、`docs: ...`。

## Pull Request

- 一个 PR 只做一件事，描述里写清动机、改动与验证方式。
- UI 改动请附截图（桌面与移动端）。
- 新依赖请说明用途，并更新 `requirements.txt` / `package.json`。
- 破坏性变更请在描述中明确标注。

## 安全问题

请勿在 Issue 中公开漏洞细节，按 [SECURITY.md](SECURITY.md) 私下反馈。
