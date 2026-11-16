import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Select, Space, Table, message } from 'antd'
import { HistoryOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'
import PageHead from '../components/PageHead'
import { formatMoney, formatPrice } from '../utils/money'

function pnlClass(v) {
  if (v == null || Number.isNaN(Number(v))) return ''
  if (Number(v) > 0) return 'is-ok'
  if (Number(v) < 0) return 'is-danger'
  return ''
}

function signedMoney(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${formatMoney(n)}`
}

function shortTime(v) {
  if (!v) return '—'
  const m = String(v).match(/\d{4}-(\d{2}-\d{2})[ T](\d{2}:\d{2})/)
  return m ? `${m[1]} ${m[2]}` : String(v)
}

const ORDER_STATUS = {
  FILLED: { label: '成交', cls: 'is-ok' },
  REJECTED: { label: '拒绝', cls: 'is-danger' },
  SUBMITTED: { label: '提交', cls: 'muted' },
  PARTIAL: { label: '部分', cls: 'muted' },
  CANCELLED: { label: '撤销', cls: 'muted' },
}

export default function Orders() {
  const [overview, setOverview] = useState(null)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [ledger, setLedger] = useState([])
  const [ledgerSymbol, setLedgerSymbol] = useState('')
  const [form] = Form.useForm()
  const [addForm] = Form.useForm()

  const refresh = async () => {
    setLoading(true)
    try {
      const [ov, ord] = await Promise.all([api.accountOverview(), api.orders()])
      setOverview(ov)
      setOrders(ord)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    form.setFieldsValue({ symbol: '600519', side: 'BUY', quantity: 100 })
    refresh().catch((e) => message.error(e.message || '加载失败'))
    const t = setInterval(() => refresh().catch(() => {}), 10000)
    return () => clearInterval(t)
  }, [])

  const positions = overview?.positions || []

  const submit = async () => {
    const values = await form.validateFields()
    const res = await api.placeOrder(values)
    if (res.success) message.success('已成交')
    else message.error(res.message || '已被风控拒绝')
    await refresh()
  }

  const liquidateAll = () => {
    Modal.confirm({
      title: '确认一键抛售全部持仓？',
      content: '将按最新价市价卖出全部持仓，此操作不可撤销。',
      okText: '确认抛售',
      okButtonProps: { danger: true },
      onOk: async () => {
        const res = await api.liquidate({ confirm: true })
        if (res.success) message.success(`已抛售 ${res.sold_count} 只`)
        else message.error(res.message || '抛售失败')
        await refresh()
      },
    })
  }

  const sellOne = (row) => {
    Modal.confirm({
      title: `抛售 ${row.symbol}？`,
      content: `将卖出全部 ${row.quantity} 股`,
      okText: '确认抛售',
      okButtonProps: { danger: true },
      onOk: async () => {
        const res = await api.liquidate({ confirm: true, symbol: row.symbol })
        if (res.success) message.success('已抛售')
        else message.error(res.message || '抛售失败')
        await refresh()
      },
    })
  }

  const addOne = (row) => {
    addForm.setFieldsValue({ quantity: 100 })
    Modal.confirm({
      title: `追加 ${row.symbol}`,
      content: (
        <Form form={addForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="quantity" label="股数（100 整数倍）" rules={[{ required: true }]}>
            <InputNumber min={100} step={100} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      ),
      onOk: async () => {
        const v = await addForm.validateFields()
        const res = await api.placeOrder({
          symbol: row.symbol,
          side: 'BUY',
          quantity: v.quantity,
          reason: 'manual_add',
        })
        if (res.success) message.success('追加成功')
        else message.error(res.message || '追加失败')
        await refresh()
      },
    })
  }

  const openLedger = async (symbol) => {
    if (ledgerSymbol === symbol) {
      setLedgerSymbol('')
      setLedger([])
      return
    }
    setLedgerSymbol(symbol)
    setLedger(await api.symbolLedger(symbol))
  }

  const unconfigured = overview?.quote_status === 'unconfigured'
  const daily = overview?.daily_pnl
  const prevEquity = overview?.total_equity != null && daily != null ? overview.total_equity - daily : null
  const dailyPct = prevEquity ? daily / prevEquity : null

  const ledgerRows = [
    { label: '持仓市值', value: overview?.market_value },
    { label: '本月盈亏', value: overview?.month_pnl, pnl: true, signed: true },
    { label: '累计盈亏', value: overview?.total_pnl, pnl: true, signed: true },
    { label: '累计佣金', value: overview?.fees, fee: true },
  ]

  return (
    <div className="panel-stack orders-desk">
      <PageHead
        extra={
          <Space>
            <Button danger onClick={liquidateAll}>一键抛售</Button>
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>刷新</Button>
          </Space>
        }
      />

      <div className="account-hero panel">
        <div className="account-hero-main">
          <div className="account-eyebrow">
            账户总资产
            {unconfigured && <span className="chip is-warn">盈亏需配置行情</span>}
          </div>
          <div className="account-equity mono">
            <span className="account-currency">¥</span>
            {overview?.total_equity == null ? '—' : formatMoney(overview.total_equity)}
          </div>
          <div className="account-delta">
            <span className={`account-delta-value mono ${unconfigured ? 'muted' : pnlClass(daily)}`}>
              {unconfigured ? '—' : signedMoney(daily)}
            </span>
            {!unconfigured && dailyPct != null && (
              <span className={`account-delta-pct ${pnlClass(daily)}`}>
                {dailyPct >= 0 ? '+' : ''}
                {(dailyPct * 100).toFixed(2)}%
              </span>
            )}
            <span className="account-delta-label">今日盈亏</span>
          </div>
          <div className="account-hero-foot">
            <span>可用现金 <b className="mono">{overview?.cash == null ? '—' : formatMoney(overview.cash)}</b></span>
            <span className="dot-sep" aria-hidden="true" />
            <span>持仓 <b className="mono">{positions.length}</b> 只</span>
          </div>
        </div>

        <dl className="account-ledger">
          {ledgerRows.map((r) => (
            <div className="account-ledger-row" key={r.label}>
              <dt>{r.label}</dt>
              <dd
                className={`mono num ${
                  r.pnl && !unconfigured ? pnlClass(r.value) : r.fee && Number(r.value) > 0 ? 'muted' : ''
                }`}
              >
                {unconfigured && r.pnl ? '—' : r.signed ? signedMoney(r.value) : r.value == null ? '—' : formatMoney(r.value)}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="desk-grid">
        <div className="desk-main">
          <div className="panel">
            <div className="panel-head">
              <h3>持仓</h3>
              <span className="chip">{positions.length} 只</span>
            </div>
            <div className="panel-body panel-body--flush">
              <Table
                rowKey="symbol"
                loading={loading}
                dataSource={positions}
                pagination={false}
                size="middle"
                expandable={{
                  expandedRowKeys: ledgerSymbol ? [ledgerSymbol] : [],
                  showExpandColumn: false,
                  expandedRowRender: () => (
                    <Table
                      size="small"
                      rowKey="id"
                      pagination={false}
                      dataSource={ledger}
                      columns={[
                        { title: '时间', dataIndex: 'created_at', width: 160, render: (v) => <span className="mono time-cell">{v || '—'}</span> },
                        { title: '类型', dataIndex: 'kind', width: 80 },
                        { title: '方向', dataIndex: 'side', width: 64 },
                        { title: '数量', dataIndex: 'quantity', width: 72, align: 'right', render: (v) => <span className="mono num">{v}</span> },
                        { title: '价格', dataIndex: 'price', width: 88, align: 'right', render: (v) => <span className="mono num">{formatPrice(v)}</span> },
                        { title: '状态', dataIndex: 'status', width: 88 },
                        { title: '说明', dataIndex: 'reason', ellipsis: true },
                      ]}
                    />
                  ),
                }}
                columns={[
                  { title: '标的', dataIndex: 'symbol', width: 96, render: (v) => <span className="mono">{v}</span> },
                  { title: '数量', dataIndex: 'quantity', width: 88, align: 'right', render: (v) => <span className="mono num">{v}</span> },
                  { title: '成本', dataIndex: 'avg_cost', width: 96, align: 'right', render: (v) => <span className="mono num">{formatPrice(v)}</span> },
                  { title: '现价', dataIndex: 'market_price', width: 96, align: 'right', render: (v) => <span className="mono num">{formatPrice(v)}</span> },
                  {
                    title: '盈亏',
                    dataIndex: 'pnl',
                    align: 'right',
                    render: (v, row) =>
                      unconfigured ? (
                        <span className="muted">—</span>
                      ) : (
                        <span className={`mono num ${pnlClass(v)}`}>
                          {formatMoney(v)}
                          <span className="pnl-pct"> {((row.pnl_pct || 0) * 100).toFixed(2)}%</span>
                        </span>
                      ),
                  },
                  {
                    title: '',
                    width: 168,
                    align: 'right',
                    render: (_, row) => (
                      <Space size={4} className="row-actions">
                        <Button size="small" type="link" onClick={() => addOne(row)}>追加</Button>
                        <Button size="small" type="link" danger onClick={() => sellOne(row)}>抛售</Button>
                        <Button
                          size="small"
                          type="link"
                          icon={<HistoryOutlined />}
                          onClick={() => openLedger(row.symbol)}
                        >
                          {ledgerSymbol === row.symbol ? '收起' : '流水'}
                        </Button>
                      </Space>
                    ),
                  },
                ]}
                locale={{
                  emptyText: (
                    <div className="empty-hint">
                      <strong>暂无持仓</strong>
                      自动交易或手工买入后会出现在这里。
                    </div>
                  ),
                }}
              />
            </div>
          </div>

          <div className="panel panel-compact">
            <div className="panel-head"><h3>下单</h3></div>
            <div className="panel-body">
              <Form form={form} layout="inline" className="order-form">
                <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '必填' }]}>
                  <Input style={{ width: 112 }} className="mono" />
                </Form.Item>
                <Form.Item name="side" label="方向" rules={[{ required: true }]}>
                  <Select
                    style={{ width: 96 }}
                    options={[
                      { value: 'BUY', label: '买入' },
                      { value: 'SELL', label: '卖出' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
                  <InputNumber min={100} step={100} />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" onClick={submit}>提交</Button>
                </Form.Item>
              </Form>
            </div>
          </div>
        </div>

        <aside className="desk-side">
          <div className="panel">
            <div className="panel-head"><h3>最近成交</h3></div>
            <div className="panel-body panel-body--flush">
              <Table
                rowKey="id"
                loading={loading}
                dataSource={orders}
                size="small"
                pagination={{ pageSize: 12, size: 'small' }}
                tableLayout="fixed"
                columns={[
                  { title: '时间', dataIndex: 'created_at', width: 96, render: (v) => <span className="mono time-cell">{shortTime(v)}</span> },
                  { title: '标的', dataIndex: 'symbol', width: 68, render: (v) => <span className="mono">{v}</span> },
                  {
                    title: '方向 / 数量',
                    dataIndex: 'side',
                    width: 84,
                    render: (v, row) => (
                      <span className="mono num">
                        {v === 'BUY' ? '买' : '卖'} {row.quantity}
                      </span>
                    ),
                  },
                  { title: '价格', dataIndex: 'filled_price', width: 70, align: 'right', render: (v) => <span className="mono num">{formatPrice(v)}</span> },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 58,
                    render: (v) => {
                      const s = ORDER_STATUS[v] || { label: v, cls: 'muted' }
                      return <span className={s.cls}>{s.label}</span>
                    },
                  },
                ]}
              />
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
