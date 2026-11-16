# AQT

> A 股量化控制台：研究、回测、SIM 与 LIVE 自动化，一个本地可运行的单用户执行台。

[![License: MIT](https://img.shields.io/badge/license-MIT-1f4b43.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-1f4b43)
![React](https://img.shields.io/badge/react-18-1f4b43)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-1f4b43)

> **风险提示**：LIVE 模式会动用真实资金，可能损失全部本金。项目默认只跑 SIM；历史回测与模拟结果不代表未来表现。本项目不构成投资建议，按 MIT 协议「按现状」提供。**使用前请完整阅读 [DISCLAIMER.md](DISCLAIMER.md)。**

## 功能

- **行情与热点**：东财热点池、iFinD / AllTick 行情、分时 / 日 K 蜡烛图。
- **情报驱动交易**：AppBuilder / Tavily / RSS / 自定义 HTTP 新闻源 → LLM 预测 → 风控闸门 → 自动下单。
- **执行**：SIM 撮合、QMT（xtquant）实盘网关、手工下单、一键抛售、持仓流水。
- **风控**：单票 / 总仓 / 同源仓位、日亏损熔断、交易间隔、黑白名单、交易日历、涨跌停 / 停牌拦截。
- **账户与告警**：持仓盈亏、对账、PushPlus 推送、风控事件留档。
- **回测**：策略回测与参数扫描 API，内置 `MaCrossStrategy`、`BreakoutStrategy`。
- **可选登录**：设置 `APP_PASSWORD` 后启用单用户登录。

## 架构

```text
React UI → FastAPI (AQT) → strategy scheduler → risk gate → Gateway
                                                 ├─ SimGateway (default)
                                                 └─ RemoteXtQuantGateway → XQA (Windows / QMT)
```

## 快速开始

依赖：Python 3.10+、Node 18+。

```bash
git clone https://github.com/June-D/aqt.git
cd aqt
cp .env.example .env
./scripts/run_dev.sh
```

- UI / API：http://127.0.0.1:8000
- 开发模式（Vite HMR）：http://127.0.0.1:5173

```bash
./scripts/run_dev.sh --dev-ui
```

首次启动会自动创建 SQLite 数据库 `data/trade.db`。冒烟测试：

```bash
./scripts/smoke.sh
```

## 配置

| 文件 | 说明 |
|------|------|
| `.env` | 端口、网关、LIVE 开关、初始资金、登录密码、LLM / 行情凭证 |
| `configs/default.yaml` | 交易时段、风控阈值、情报规则、热点池、新闻源 |
| `configs/calendar.yaml` | 交易日历（节假日 / 补班） |

常用环境变量：

```env
APP_PORT=8000
GATEWAY_TYPE=sim            # sim | remote_xtquant
LIVE_TRADING_ENABLED=false  # 实盘总开关
INITIAL_CASH=1000000
APP_PASSWORD=               # 留空则本机免登录

# LLM（OpenAI 兼容）
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
# 资讯
APPBUILDER_TOKEN=
TAVILY_API_KEY=
```

行情源（iFinD / AllTick / Tushare）在 `configs/default.yaml` 的 `market_data` 中配置，也可在 UI「设置 → 行情 / K线」里填写。

实盘相关：

```env
GATEWAY_TYPE=remote_xtquant
GATEWAY_URL=http://<windows-ip>:8100
GATEWAY_TOKEN=change-me
LIVE_TRADING_ENABLED=false
```

即使网关指向远端，LIVE 未开启前订单仍会被拦截。

## Windows XQA（QMT 实盘代理）

完整步骤见 [docs/部署与使用说明.md](docs/部署与使用说明.md) 与 [agent/README.md](agent/README.md)。

1. 安装券商终端并登录。
2. 配置 `GATEWAY_TOKEN`、`QMT_ACCOUNT_ID`、`QMT_USERDATA_PATH`。
3. 在仓库根目录运行 `python -m agent.main`。
4. 把控制面的 `GATEWAY_*` 指向 Windows 机器。
5. 确认 `/health` 正常后再在 UI 开启 LIVE。

未安装 `xtquant` 时 Agent 仍可启动，但会明确拒绝下单，不会假装成交。

## 项目结构

```text
backend/app/   FastAPI、回测、SIM、风控、Gateway
frontend/      React + Ant Design + Vite
agent/         Windows XQA 执行代理（xtquant）
configs/       交易 / 风控 / 日历 YAML
scripts/       run_dev / smoke
docs/          部署、入门与情报交易说明
tests/         pytest
```

## 测试

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

## 文档

- [部署与使用说明](docs/部署与使用说明.md)
- [新手入门](docs/新手入门.md)
- [情报交易](docs/情报交易.md)
- [设计说明](DESIGN.md)
- [免责声明](DISCLAIMER.md)

## 贡献

欢迎 Issue 与 PR，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。涉及风控、下单路径的改动请附带测试。

## 安全

请勿在 Issue 中粘贴 API Key、账号或持仓数据。漏洞与安全问题请按 [SECURITY.md](SECURITY.md) 私下反馈。

## 免责声明

本项目不构成投资建议，不保证第三方行情、资讯、LLM 与券商接口的准确性或可用性。LIVE 交易可能导致本金损失，所有交易决策及其后果由使用者自行承担；请自行确保使用行为符合当地法律法规与第三方服务条款。完整条款见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

[MIT](LICENSE) © 2026 June-D
