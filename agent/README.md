# XQA（Windows 执行代理）

1. 安装券商终端并登录
2. Windows Python：`pip install -r requirements.txt`
3. 环境变量：
   - `GATEWAY_TOKEN` 与控制面相同
   - `QMT_ACCOUNT_ID`
   - `QMT_USERDATA_PATH`（miniQMT userdata 目录）
4. 仓库根目录：`python -m agent.main`
5. 控制面 `.env`：
   - `GATEWAY_TYPE=remote_xtquant`
   - `GATEWAY_URL=http://<windows-ip>:8100`
   - `GATEWAY_TOKEN=<same>`
   - UI 打开 LIVE

无 xtquant 时 Agent 仍可启动：`/health` 会标明 `wired=false`，下单返回明确拒绝，不会假装成交。
