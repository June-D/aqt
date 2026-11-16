import { useCallback, useEffect, useState } from 'react'
import { Button, Table, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'
import PageHead from '../components/PageHead'

const ACTION_LABEL = {
  PREDICT_ONLY: '仅预测',
  BUY: '买入',
  SELL: '卖出',
  SKIP: '跳过',
  BUY_OK: '买入成交',
  SELL_OK: '卖出成交',
  BUY_REJECT: '买入被拒',
  SELL_REJECT: '卖出被拒',
}

const RUN_STATUS = {
  DONE: { label: '完成', cls: 'is-ok' },
  RUNNING: { label: '运行中', cls: 'is-accent' },
  BLOCKED: { label: '阻塞', cls: 'is-warn' },
  ERROR: { label: '错误', cls: 'is-danger' },
}

function shortTime(v) {
  if (!v) return '-'
  const m = String(v).match(/\d{4}-(\d{2}-\d{2})[ T](\d{2}:\d{2})/)
  return m ? `${m[1]} ${m[2]}` : String(v)
}

function DirectionBadge({ value }) {
  const up = value === 'UP'
  const down = value === 'DOWN'
  const cls = up ? 'is-up' : down ? 'is-down' : 'is-flat'
  const label = up ? '看涨' : down ? '看跌' : '中性'
  return <span className={`dir-badge ${cls}`}>{label}</span>
}

function Confidence({ value }) {
  const n = Math.max(0, Math.min(1, Number(value) || 0))
  const pct = Math.round(n * 100)
  return (
    <span className="conf">
      <span className="conf-bar">
        <span className={`conf-fill ${n >= 0.7 ? 'is-high' : ''}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="conf-num mono">{n.toFixed(2)}</span>
    </span>
  )
}

export default function Intel() {
  const [status, setStatus] = useState({})
  const [news, setNews] = useState([])
  const [preds, setPreds] = useState([])
  const [runs, setRuns] = useState([])
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    const [st, n, p, r] = await Promise.all([
      api.intelStatus(),
      api.intelNews(),
      api.intelPredictions(),
      api.intelRuns(),
    ])
    setStatus(st)
    setNews(n)
    setPreds(p)
    setRuns(r)
  }, [])

  useEffect(() => {
    refresh().catch((e) => message.error(e.message || '加载失败'))
  }, [refresh])

  return (
    <div className="panel-stack intel-page">
      <PageHead
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setBusy(true)
              refresh()
                .catch((e) => message.error(e.message || '加载失败'))
                .finally(() => setBusy(false))
            }}
            loading={busy}
          >
            刷新
          </Button>
        }
      >
        <span className="head-chips">
          <span className={`chip ${status.enabled ? 'is-ok' : ''}`}>自动交易{status.enabled ? '开' : '关'}</span>
          <span className="chip">热点池 {status.whitelist_count || 0} 只</span>
          <span className="chip">调度 {status.poll_interval_seconds || 300}s</span>
        </span>
      </PageHead>

      <div className="desk-grid">
        <div className="desk-main">
          <div className="panel">
            <div className="panel-head"><h3>最近预测</h3></div>
            <div className="panel-body panel-body--flush">
              <Table
                rowKey="id"
                size="middle"
                dataSource={preds}
                pagination={{ pageSize: 10, size: 'small' }}
                tableLayout="fixed"
                columns={[
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    width: 118,
                    className: 'col-nowrap',
                    render: (v) => <span className="mono time-cell">{shortTime(v)}</span>,
                  },
                  {
                    title: '代码',
                    dataIndex: 'symbol',
                    width: 68,
                    className: 'col-nowrap',
                    render: (v) => <span className="mono">{v}</span>,
                  },
                  {
                    title: '方向',
                    dataIndex: 'direction',
                    width: 64,
                    className: 'col-nowrap',
                    render: (v) => <DirectionBadge value={v} />,
                  },
                  {
                    title: '置信度',
                    dataIndex: 'confidence',
                    width: 100,
                    className: 'col-nowrap',
                    render: (v) => <Confidence value={v} />,
                  },
                  { title: '行业', dataIndex: 'sector', width: 82, className: 'col-nowrap', render: (v) => v || '—' },
                  {
                    title: '动作',
                    dataIndex: 'action',
                    width: 108,
                    className: 'col-nowrap',
                    render: (v) => {
                      const cls = v?.endsWith('_OK')
                        ? 'is-ok'
                        : v?.endsWith('_REJECT')
                          ? 'is-danger'
                          : ''
                      return <span className={cls}>{ACTION_LABEL[v] || v || '—'}</span>
                    },
                  },
                  {
                    title: '理由',
                    dataIndex: 'reason',
                    className: 'col-ellipsis',
                    ellipsis: { showTitle: true },
                  },
                ]}
              />
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h3>自动下单 / 运行记录</h3></div>
            <div className="panel-body panel-body--flush">
              <Table
                rowKey="id"
                size="small"
                dataSource={runs}
                pagination={{ pageSize: 8, size: 'small' }}
                tableLayout="fixed"
                columns={[
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    width: 118,
                    className: 'col-nowrap',
                    render: (v) => <span className="mono time-cell">{shortTime(v)}</span>,
                  },
                  { title: 'ID', dataIndex: 'id', width: 56, className: 'col-nowrap', render: (v) => <span className="mono num">{v}</span> },
                  { title: '状态', dataIndex: 'status', width: 76, className: 'col-nowrap', render: (v) => {
                    const s = RUN_STATUS[v] || { label: v || '-', cls: 'muted' }
                    return <span className={s.cls}>{s.label}</span>
                  } },
                  { title: '新闻', dataIndex: 'news_count', width: 56, align: 'right', className: 'col-nowrap', render: (v) => <span className="mono num">{v ?? 0}</span> },
                  { title: '预测', dataIndex: 'pred_count', width: 56, align: 'right', className: 'col-nowrap', render: (v) => <span className="mono num">{v ?? 0}</span> },
                  { title: '下单', dataIndex: 'order_count', width: 56, align: 'right', className: 'col-nowrap', render: (v) => <span className="mono num">{v ?? 0}</span> },
                  {
                    title: '说明',
                    dataIndex: 'message',
                    className: 'col-ellipsis',
                    ellipsis: { showTitle: true },
                  },
                ]}
              />
            </div>
          </div>
        </div>

        <aside className="desk-side">
          <div className="panel">
            <div className="panel-head">
              <h3>新闻</h3>
              <span className="chip">{news.length} 条</span>
            </div>
            <div className="panel-body panel-body--flush">
              <Table
                rowKey="id"
                size="small"
                dataSource={news}
                pagination={{ pageSize: 12, size: 'small' }}
                tableLayout="fixed"
                columns={[
                  { title: '来源', dataIndex: 'source', width: 88, className: 'col-nowrap' },
                  {
                    title: '标题',
                    dataIndex: 'title',
                    className: 'col-ellipsis',
                    ellipsis: { showTitle: true },
                    render: (title, row) =>
                      row.url ? (
                        <a
                          className="news-link"
                          href={row.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={title || ''}
                        >
                          {title}
                        </a>
                      ) : (
                        title || '-'
                      ),
                  },
                  {
                    title: '时间',
                    dataIndex: 'published_at',
                    width: 110,
                    className: 'col-nowrap',
                    render: (_, row) => (
                      <span className="mono time-cell">{shortTime(row.published_at || row.created_at)}</span>
                    ),
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
