import { useEffect, useState } from 'react'
import { Button, Input, InputNumber, Modal, Select, Switch, message } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { api } from '../api'
import PageHead from '../components/PageHead'

const SECTIONS = [
  { id: 'trading', title: '交易模式', hint: 'SIM / LIVE 切换' },
  { id: 'llm', title: 'LLM', hint: '模型与 API' },
  { id: 'intel', title: '情报源 / 规则', hint: '自动交易阈值' },
  { id: 'hot_pool', title: '热点源', hint: '池子与白名单' },
  { id: 'market_data', title: '行情 / K线', hint: 'iFinD / AllTick' },
  { id: 'alerts', title: '风控推送', hint: 'PushPlus' },
  { id: 'sim', title: '模拟资金', hint: '账本重置' },
  { id: 'broker', title: '券商 QMT', hint: '实盘网关' },
]

export default function Settings() {
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [forms, setForms] = useState({})
  const [active, setActive] = useState('trading')

  const load = async () => {
    const data = await api.getSettings()
    setCfg(data)
    setForms({
      trading: { mode: data.trading?.mode || 'sim' },
      llm: {
        base_url: data.llm?.base_url,
        model: data.llm?.model,
        api_key: '',
      },
      intel: {
        enabled: !!data.intel?.enabled,
        poll_interval_seconds: data.intel?.poll_interval_seconds ?? 300,
        min_confidence: data.intel?.min_confidence ?? 0.7,
        sell_mode: data.intel?.sell_mode || 'all',
        trade_pct: data.intel?.trade_pct ?? 0.1,
        max_holdings: data.intel?.max_holdings ?? 10,
        max_orders_per_day: data.intel?.max_orders_per_day ?? 30,
        allow_auto_sell: data.intel?.allow_auto_sell !== false,
        news_provider: data.intel?.news_provider || 'appbuilder',
      },
      hot_pool: {
        enabled: data.hot_pool?.enabled !== false,
        top_n: data.hot_pool?.top_n ?? 80,
        mode: data.hot_pool?.mode || 'merge',
        extra_symbols: (data.hot_pool?.extra_symbols || []).join(','),
      },
      market_data: {
        provider: data.market_data?.provider || 'ifind',
        ifind_refresh_token: data.market_data?.ifind?.refresh_token || '',
        ifind_base_url: data.market_data?.ifind?.base_url || 'https://quantapi.51ifind.com/api/v1',
        alltick_token: data.market_data?.alltick?.token || '',
        alltick_base_url: data.market_data?.alltick?.base_url || 'https://quote.alltick.co',
        tushare_token: data.market_data?.tushare?.token || '',
      },
      alerts: {
        pushplus_token: data.alerts?.pushplus_token || '',
        pushplus_topic: data.alerts?.pushplus_topic || '',
      },
      sim: { initial_cash: data.sim?.initial_cash ?? 1000000 },
      broker: {
        gateway_url: data.broker?.gateway_url || '',
      },
    })
  }

  useEffect(() => {
    load().catch((e) => message.error(e.message || '加载失败'))
  }, [])

  const save = async (section, data, password) => {
    setBusy(true)
    try {
      const body = { section, data }
      if (password != null) body.password = password
      const next = await api.putSettings(body)
      setCfg(next)
      message.success('已保存')
      window.dispatchEvent(new Event('aqt-status-changed'))
      await load()
    } catch (e) {
      message.error(e.message || '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const saveTrading = async () => {
    const mode = forms.trading?.mode || 'sim'
    if (mode === 'live') {
      let password = ''
      Modal.confirm({
        title: '开启 LIVE 实盘',
        content: (
          <div>
            <p>将使用真实资金通过 QMT 下单。请再次输入登录密码确认。</p>
            <Input.Password
              placeholder="登录密码"
              onChange={(e) => {
                password = e.target.value
              }}
            />
          </div>
        ),
        okText: '确认开启 LIVE',
        okButtonProps: { danger: true },
        onOk: async () => save('trading', { mode: 'live' }, password),
      })
      return
    }
    await save('trading', { mode: 'sim' })
  }

  if (!cfg || !forms.trading) {
    return (
      <div className="panel-stack">
        <PageHead>加载中…</PageHead>
      </div>
    )
  }

  const section = SECTIONS.find((s) => s.id === active) || SECTIONS[0]

  const renderBody = () => {
    switch (active) {
      case 'trading':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">运行模式</div>
                <div className="setting-desc">SIM 用真行情模拟成交；LIVE 经 QMT 实盘下单。</div>
              </div>
              <div className="setting-control">
                <Select
                  style={{ width: 260 }}
                  value={forms.trading.mode}
                  options={[
                    { value: 'sim', label: 'SIM（真行情模拟成交）' },
                    { value: 'live', label: 'LIVE（QMT 实盘）' },
                  ]}
                  onChange={(mode) => setForms((f) => ({ ...f, trading: { mode } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button type="primary" loading={busy} onClick={saveTrading} icon={<SaveOutlined />}>
                保存模式
              </Button>
            </div>
          </>
        )
      case 'llm':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">API Base URL</div>
                <div className="setting-desc">兼容 OpenAI 协议的推理端点。</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.llm.base_url}
                  onChange={(e) => setForms((f) => ({ ...f, llm: { ...f.llm, base_url: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">模型</div>
                <div className="setting-desc">例如 qwen3.5-flash、gpt-4o-mini。</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.llm.model}
                  onChange={(e) => setForms((f) => ({ ...f, llm: { ...f.llm, model: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">API Key</div>
                <div className="setting-desc">{cfg.llm?.configured ? '已配置；留空则保留原值。' : '尚未配置，保存时必填。'}</div>
              </div>
              <div className="setting-control">
                <Input.Password
                  value={forms.llm.api_key}
                  onChange={(e) => setForms((f) => ({ ...f, llm: { ...f.llm, api_key: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button type="primary" loading={busy} onClick={() => save('llm', forms.llm)} icon={<SaveOutlined />}>
                保存 LLM
              </Button>
            </div>
          </>
        )
      case 'intel':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">自动交易</div>
                <div className="setting-desc">关闭后仅采集与预测，不自动下单。</div>
              </div>
              <div className="setting-control">
                <Switch
                  checked={!!forms.intel.enabled}
                  onChange={(enabled) => setForms((f) => ({ ...f, intel: { ...f.intel, enabled } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">调度间隔（秒）</div>
                <div className="setting-desc">情报管道轮询周期，最小 60。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={60}
                  value={forms.intel.poll_interval_seconds}
                  onChange={(v) => setForms((f) => ({ ...f, intel: { ...f.intel, poll_interval_seconds: v } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">最低置信度</div>
                <div className="setting-desc">低于阈值的预测不会触发下单。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={0}
                  max={1}
                  step={0.05}
                  value={forms.intel.min_confidence}
                  onChange={(v) => setForms((f) => ({ ...f, intel: { ...f.intel, min_confidence: v } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">卖出模式</div>
                <div className="setting-desc">看跌信号时全部清仓或按比例减仓。</div>
              </div>
              <div className="setting-control">
                <Select
                  style={{ width: 180 }}
                  value={forms.intel.sell_mode}
                  options={[
                    { value: 'all', label: '全部卖出' },
                    { value: 'pct', label: '按比例减仓' },
                  ]}
                  onChange={(sell_mode) => setForms((f) => ({ ...f, intel: { ...f.intel, sell_mode } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">单笔资金比例</div>
                <div className="setting-desc">买入占用可用现金的比例（trade_pct）。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={0.01}
                  max={1}
                  step={0.01}
                  value={forms.intel.trade_pct}
                  onChange={(v) => setForms((f) => ({ ...f, intel: { ...f.intel, trade_pct: v } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">最大持仓只数</div>
                <div className="setting-desc">超过后不再开新仓。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={1}
                  value={forms.intel.max_holdings}
                  onChange={(v) => setForms((f) => ({ ...f, intel: { ...f.intel, max_holdings: v } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">允许自动卖出</div>
                <div className="setting-desc">关闭后自动侧只买不卖。</div>
              </div>
              <div className="setting-control">
                <Switch
                  checked={!!forms.intel.allow_auto_sell}
                  onChange={(allow_auto_sell) => setForms((f) => ({ ...f, intel: { ...f.intel, allow_auto_sell } }))}
                />
              </div>
            </div>
            <p className="control-note">AppBuilder Token 请在环境变量 APPBUILDER_TOKEN 配置；未配置时本轮情报失败并告警。</p>
            <div className="setting-actions">
              <Button type="primary" loading={busy} onClick={() => save('intel', forms.intel)} icon={<SaveOutlined />}>
                保存情报规则
              </Button>
            </div>
          </>
        )
      case 'hot_pool':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">启用东财人气 / 飙升</div>
                <div className="setting-desc">从东方财富拉取热点池。</div>
              </div>
              <div className="setting-control">
                <Switch
                  checked={!!forms.hot_pool.enabled}
                  onChange={(enabled) => setForms((f) => ({ ...f, hot_pool: { ...f.hot_pool, enabled } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">Top N</div>
                <div className="setting-desc">热点池保留的最大标的数。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={10}
                  value={forms.hot_pool.top_n}
                  onChange={(v) => setForms((f) => ({ ...f, hot_pool: { ...f.hot_pool, top_n: v } }))}
                />
              </div>
            </div>
            <div className="setting-row setting-row--stack">
              <div className="setting-meta">
                <div className="setting-title">额外永远允许</div>
                <div className="setting-desc">逗号分隔代码，始终进入可交易池。</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.hot_pool.extra_symbols}
                  onChange={(e) => setForms((f) => ({ ...f, hot_pool: { ...f.hot_pool, extra_symbols: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button
                type="primary"
                loading={busy}
                icon={<SaveOutlined />}
                onClick={() =>
                  save('hot_pool', {
                    ...forms.hot_pool,
                    extra_symbols: String(forms.hot_pool.extra_symbols || '')
                      .split(/[,，\s]+/)
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
              >
                保存热点源
              </Button>
            </div>
          </>
        )
      case 'market_data':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">提供商</div>
                <div className="setting-desc">默认 iFinD；AllTick 备选；Tushare 预留。</div>
              </div>
              <div className="setting-control">
                <Select
                  style={{ width: 260 }}
                  value={forms.market_data.provider}
                  options={[
                    { value: 'ifind', label: '同花顺 iFinD（默认）' },
                    { value: 'alltick', label: 'AllTick（备选）' },
                    { value: 'tushare', label: 'Tushare（槽位预留）' },
                  ]}
                  onChange={(provider) => setForms((f) => ({ ...f, market_data: { ...f.market_data, provider } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">iFinD refresh_token</div>
                <div className="setting-desc">超级命令「账号详情」获取；留空保存则保留原值。</div>
              </div>
              <div className="setting-control">
                <Input.Password
                  value={forms.market_data.ifind_refresh_token}
                  onChange={(e) =>
                    setForms((f) => ({ ...f, market_data: { ...f.market_data, ifind_refresh_token: e.target.value } }))
                  }
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">iFinD Base URL</div>
                <div className="setting-desc">默认 https://quantapi.51ifind.com/api/v1</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.market_data.ifind_base_url}
                  onChange={(e) =>
                    setForms((f) => ({ ...f, market_data: { ...f.market_data, ifind_base_url: e.target.value } }))
                  }
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">AllTick Token</div>
                <div className="setting-desc">备选行情源；留空保存保留原值。</div>
              </div>
              <div className="setting-control">
                <Input.Password
                  value={forms.market_data.alltick_token}
                  onChange={(e) => setForms((f) => ({ ...f, market_data: { ...f.market_data, alltick_token: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">AllTick Base URL</div>
                <div className="setting-desc">默认 https://quote.alltick.co</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.market_data.alltick_base_url}
                  onChange={(e) => setForms((f) => ({ ...f, market_data: { ...f.market_data, alltick_base_url: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">Tushare Token</div>
                <div className="setting-desc">预留，尚未接入行情路径。</div>
              </div>
              <div className="setting-control">
                <Input.Password
                  value={forms.market_data.tushare_token}
                  onChange={(e) => setForms((f) => ({ ...f, market_data: { ...f.market_data, tushare_token: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button
                type="primary"
                loading={busy}
                icon={<SaveOutlined />}
                onClick={() =>
                  save('market_data', {
                    provider: forms.market_data.provider,
                    ifind: {
                      refresh_token: forms.market_data.ifind_refresh_token,
                      base_url: forms.market_data.ifind_base_url,
                    },
                    alltick: {
                      token: forms.market_data.alltick_token,
                      base_url: forms.market_data.alltick_base_url,
                    },
                    tushare: { token: forms.market_data.tushare_token },
                  })
                }
              >
                保存行情配置
              </Button>
            </div>
          </>
        )
      case 'alerts':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">PushPlus Token</div>
                <div className="setting-desc">风控拒单与告警推送凭证。</div>
              </div>
              <div className="setting-control">
                <Input.Password
                  value={forms.alerts.pushplus_token}
                  onChange={(e) => setForms((f) => ({ ...f, alerts: { ...f.alerts, pushplus_token: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">Topic</div>
                <div className="setting-desc">可选群组主题；个人推送可留空。</div>
              </div>
              <div className="setting-control">
                <Input
                  value={forms.alerts.pushplus_topic}
                  onChange={(e) => setForms((f) => ({ ...f, alerts: { ...f.alerts, pushplus_topic: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button type="primary" loading={busy} onClick={() => save('alerts', forms.alerts)} icon={<SaveOutlined />}>
                保存推送
              </Button>
            </div>
          </>
        )
      case 'sim':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">初始资金</div>
                <div className="setting-desc">修改并保存将清仓、清流水后重置账本。</div>
              </div>
              <div className="setting-control">
                <InputNumber
                  min={10000}
                  step={10000}
                  style={{ width: 200 }}
                  value={forms.sim.initial_cash}
                  onChange={(v) => setForms((f) => ({ ...f, sim: { initial_cash: v } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button
                danger
                loading={busy}
                onClick={() =>
                  Modal.confirm({
                    title: '重置模拟账本？',
                    content: `现金将设为 ${forms.sim.initial_cash}，持仓与流水清空。`,
                    onOk: () => save('sim', { initial_cash: forms.sim.initial_cash, reset: true }),
                  })
                }
              >
                保存并重置账本
              </Button>
            </div>
          </>
        )
      case 'broker':
        return (
          <>
            <div className="setting-row">
              <div className="setting-meta">
                <div className="setting-title">Gateway URL</div>
                <div className="setting-desc">XtQuant / QMT 远程网关。Token 也可写在 .env。</div>
              </div>
              <div className="setting-control">
                <Input
                  className="mono"
                  value={forms.broker.gateway_url}
                  onChange={(e) => setForms((f) => ({ ...f, broker: { gateway_url: e.target.value } }))}
                />
              </div>
            </div>
            <div className="setting-actions">
              <Button type="primary" loading={busy} onClick={() => save('broker', forms.broker)} icon={<SaveOutlined />}>
                保存券商
              </Button>
            </div>
          </>
        )
      default:
        return null
    }
  }

  return (
    <div className="panel-stack settings-page">
      <PageHead
        extra={<Button icon={<ReloadOutlined />} onClick={() => load()} loading={busy}>刷新</Button>}
      />

      <div className="settings-shell">
        <nav className="settings-toc" aria-label="设置分区">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`settings-toc-item ${active === s.id ? 'is-active' : ''}`}
              onClick={() => setActive(s.id)}
            >
              <span className="settings-toc-title">{s.title}</span>
              <span className="settings-toc-hint">{s.hint}</span>
            </button>
          ))}
        </nav>

        <section className="settings-pane panel">
          <div className="settings-pane-head">
            <h3>{section.title}</h3>
            <p>{section.hint}</p>
          </div>
          <div className="settings-pane-body">{renderBody()}</div>
        </section>
      </div>
    </div>
  )
}
