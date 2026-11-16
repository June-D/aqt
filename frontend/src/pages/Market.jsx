import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Input, Select, Table, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'
import PageHead from '../components/PageHead'
import CandleChart from '../components/CandleChart'
import { formatPrice } from '../utils/money'

function formatVolume(v) {
  const n = Number(v) || 0
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`
  if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 万`
  return String(Math.round(n))
}

export default function Market() {
  const [board, setBoard] = useState(null)
  const [period, setPeriod] = useState('5m')
  const [focus, setFocus] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async (sym, p, silent = false) => {
    const target = sym ?? focus
    const per = p ?? period
    if (!silent) setLoading(true)
    try {
      const data = await api.marketBoard({ symbol: target || undefined, period: per })
      setBoard(data)
      if (!target && data.focus) setFocus(data.focus)
    } catch (e) {
      message.error(e.message || '加载失败')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(() => load(undefined, undefined, true), 10000)
    return () => clearInterval(t)
  }, [])

  const quoteStatus = board?.quotes?.status
  const klineStatus = board?.kline?.status
  const bars = board?.kline?.bars || []
  const hotRows = board?.hot_rows || []

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return hotRows
    return hotRows.filter((row) => {
      const blob = `${row.symbol || ''} ${row.name || ''} ${row.industry || ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [hotRows, query])

  const focusName = hotRows.find((r) => r.symbol === focus)?.name || ''
  const lastBar = bars.length ? bars[bars.length - 1] : null

  return (
    <div className="panel-stack">
      <PageHead
        extra={
          <div className="toolbar">
            <Select
              style={{ width: 118 }}
              value={period}
              options={[
                { value: '1m', label: '分时 / 1m' },
                { value: '5m', label: '5 分钟' },
                { value: '15m', label: '15 分钟' },
                { value: 'day', label: '日 K' },
              ]}
              onChange={(p) => {
                setPeriod(p)
                load(focus, p)
              }}
            />
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => load(focus, period)}>
              刷新
            </Button>
          </div>
        }
      />

      <div className="market-layout">
        <aside className="market-side">
          <div className="panel">
            <div className="panel-head">
              <h3>热点</h3>
              <span className={`chip ${quoteStatus === 'ok' ? 'is-ok' : 'is-warn'}`}>
                {quoteStatus === 'unconfigured' ? '报价待配置' : `${filtered.length}/${hotRows.length} 只`}
              </span>
            </div>
            <div className="hot-search">
              <Input.Search
                allowClear
                placeholder="搜索代码 / 名称 / 行业"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="panel-body panel-body--flush">
              <Table
                size="small"
                rowKey="symbol"
                loading={loading}
                tableLayout="fixed"
                pagination={{ pageSize: 15, size: 'small', showSizeChanger: false }}
                dataSource={filtered}
                onRow={(row) => ({
                  onClick: () => {
                    setFocus(row.symbol)
                    load(row.symbol, period)
                  },
                })}
                rowClassName={(row) => (row.symbol === focus ? 'hot-row-active' : '')}
                columns={[
                  {
                    title: '代码',
                    dataIndex: 'symbol',
                    width: 76,
                    className: 'col-nowrap',
                    render: (v) => <span className="mono">{v}</span>,
                  },
                  {
                    title: '名称',
                    dataIndex: 'name',
                    className: 'col-ellipsis',
                    ellipsis: { showTitle: true },
                    render: (v) => v || '—',
                  },
                  {
                    title: '行业',
                    dataIndex: 'industry',
                    width: 86,
                    className: 'col-ellipsis',
                    ellipsis: { showTitle: true },
                    render: (v) => v || '—',
                  },
                  {
                    title: '现价',
                    dataIndex: 'price',
                    width: 88,
                    align: 'right',
                    className: 'col-nowrap',
                    render: (v) =>
                      v == null ? <span className="muted">—</span> : <span className="mono num">{formatPrice(v)}</span>,
                  },
                ]}
                locale={{ emptyText: query ? '没有匹配的热点' : '热点池为空，请在设置配置热点源并等待调度刷新' }}
              />
            </div>
          </div>
        </aside>

        <div className="market-main">
          <div className="panel">
            <div className="panel-head chart-head">
              <div className="chart-head-title">
                <h3>{focusName || focus || 'K 线'}</h3>
                {focus && <span className="chart-head-symbol mono">{focus}</span>}
              </div>
              <span className={`chip ${klineStatus === 'ok' ? 'is-ok' : 'is-warn'}`}>
                {klineStatus === 'ok' ? 'AllTick' : klineStatus === 'unconfigured' ? '待配置行情源' : klineStatus || '—'}
              </span>
            </div>
            <div className="panel-body">
              {klineStatus === 'unconfigured' ? (
                <Empty
                  description={
                    <span>
                      请到 <a href="/settings">设置</a> 填写行情 Token
                    </span>
                  }
                />
              ) : bars.length ? (
                <>
                  {lastBar && (
                    <div className="chart-stats">
                      <div className="chart-stat">
                        <span className="chart-stat-label">最新</span>
                        <span className="chart-stat-value mono num">{formatPrice(lastBar.close)}</span>
                      </div>
                      <div className="chart-stat">
                        <span className="chart-stat-label">开</span>
                        <span className="chart-stat-value mono num">{formatPrice(lastBar.open)}</span>
                      </div>
                      <div className="chart-stat">
                        <span className="chart-stat-label">高</span>
                        <span className="chart-stat-value mono num">{formatPrice(lastBar.high)}</span>
                      </div>
                      <div className="chart-stat">
                        <span className="chart-stat-label">低</span>
                        <span className="chart-stat-value mono num">{formatPrice(lastBar.low)}</span>
                      </div>
                      <div className="chart-stat">
                        <span className="chart-stat-label">量</span>
                        <span className="chart-stat-value mono num">{formatVolume(lastBar.volume)}</span>
                      </div>
                      <div className="chart-stat chart-stat--side">
                        <span className="chart-stat-label">周期</span>
                        <span className="chart-stat-value mono">{period}</span>
                      </div>
                    </div>
                  )}
                  <CandleChart bars={bars} />
                </>
              ) : (
                <Empty description={board?.kline?.message || '暂无 K 线'} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
