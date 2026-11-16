import { useEffect, useState } from 'react'
import { Button, Space, Table, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'
import PageHead from '../components/PageHead'

const EVENT_LABEL = {
  MAX_POSITION: '单票超限',
  MAX_TOTAL_POSITION: '总仓超限',
  MAX_STRATEGY_POSITION: '同源仓超限',
  MAX_ORDER: '单笔超限',
  DAILY_LOSS: '日亏损熔断',
  MIN_INTERVAL: '交易间隔',
  WHITELIST: '白名单',
  BLACKLIST: '黑名单',
  LIVE_DISABLED: 'LIVE 关闭',
  CIRCUIT: '熔断',
  REJECT: '拒单',
  CASH: '资金不足',
  LOT_SIZE: '手数不合规',
  CALENDAR: '非交易日',
  SESSION: '非交易时段',
  HALT: '停牌',
  LIMIT_UP: '涨停',
  LIMIT_DOWN: '跌停',
}

const HARD_EVENTS = new Set([
  'DAILY_LOSS',
  'CIRCUIT',
  'REJECT',
  'CASH',
  'HALT',
  'LIMIT_UP',
  'LIMIT_DOWN',
  'LIVE_DISABLED',
])

const PUSH_LABEL = {
  ok: '已推送',
  failed: '推送失败',
  unconfigured: '推送未配置',
  pending: '待推送',
}

export default function RiskEvents() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      setRows(await api.riskAlerts())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch((e) => message.error(e.message || '加载失败'))
  }, [])

  return (
    <div className="panel-stack">
      <PageHead
        extra={
          <Space>
            <span className="chip">{rows.length} 条</span>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          </Space>
        }
      />
      <div className="panel">
        <div className="panel-body panel-body--flush">
          <Table
            rowKey="id"
            loading={loading}
            dataSource={rows}
            size="middle"
            locale={{
              emptyText: (
                <div className="empty-hint">
                  <strong>暂无风控 / 告警</strong>
                  被拦截的订单与推送记录会出现在这里。
                </div>
              ),
            }}
            columns={[
              { title: '时间', dataIndex: 'created_at', width: 176, render: (v) => <span className="mono time-cell">{v || '-'}</span> },
              {
                title: '类型',
                dataIndex: 'event_type',
                width: 132,
                render: (v) => (
                  <span className={`chip ${HARD_EVENTS.has(v) ? 'is-danger' : 'is-warn'}`} title={v}>
                    {EVENT_LABEL[v] || v}
                  </span>
                ),
              },
              { title: '标的', dataIndex: 'symbol', width: 100, render: (v) => <span className="mono">{v || '-'}</span> },
              { title: '说明', dataIndex: 'message' },
              {
                title: '推送',
                dataIndex: 'push_status',
                width: 116,
                render: (v) => <span className={v === 'failed' ? 'is-danger' : v === 'ok' ? 'is-ok' : 'muted'}>{PUSH_LABEL[v] || v || '-'}</span>,
              },
            ]}
          />
        </div>
      </div>
    </div>
  )
}
