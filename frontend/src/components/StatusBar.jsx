import { Popover, Spin } from 'antd'

/** 顶栏精简状态：模式 + 自动 + 配置摘要（详情悬浮） */
export default function StatusBar({ status, loading }) {
  if (loading || !status) {
    return (
      <div className="aqt-status-row" aria-live="polite">
        <Spin size="small" />
      </div>
    )
  }

  const isSim = (status.mode || 'sim') === 'sim'
  const auto = !!status.auto_trade_enabled
  const liveOn = !!status.live_trading_enabled
  const gwOk = status?.gateway_health?.ok ?? status?.broker_status === 'ok'

  const checks = [
    { key: 'LLM', ok: !!status.llm_configured },
    { key: '情报源', ok: !!status.intel_source_configured },
    { key: '行情', ok: status.market_data_status === 'configured' },
    { key: '推送', ok: status.push_status === 'configured' },
    { key: '券商', ok: !!gwOk },
  ]
  const missing = checks.filter((c) => !c.ok)

  const detail = (
    <ul className="status-popover-list">
      {checks.map((c) => (
        <li key={c.key} className={c.ok ? 'is-ok' : 'is-warn'}>
          {c.key} {c.ok ? '已就绪' : '待配置'}
        </li>
      ))}
    </ul>
  )

  return (
    <div className="aqt-status-row" aria-live="polite">
      <span className={`chip ${isSim ? 'is-accent' : 'is-warn'}`}>{isSim ? '模拟' : '实盘'}</span>
      <span className={`chip ${auto ? 'is-ok' : ''}`}>自动{auto ? '开' : '关'}</span>
      <span className={`chip ${liveOn ? 'is-warn' : ''}`}>LIVE{liveOn ? '开' : '关'}</span>
      <Popover content={detail} title="系统配置" placement="bottomRight">
        <button type="button" className={`chip chip-btn ${missing.length ? 'is-warn' : 'is-ok'}`}>
          {missing.length ? `待配 ${missing.length}` : '配置齐'}
        </button>
      </Popover>
    </div>
  )
}
