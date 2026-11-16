import { useEffect, useMemo, useRef, useState } from 'react'
import { formatPrice } from '../utils/money'

const HEIGHT = 300
const M = { t: 16, r: 64, b: 24, l: 12 }
const VOL_H = 46
const GAP = 12

function timeLabel(ts) {
  if (ts == null || ts === '') return ''
  if (typeof ts === 'number') {
    const ms = ts < 1e12 ? ts * 1000 : ts
    const d = new Date(ms)
    if (Number.isNaN(d.getTime())) return String(ts)
    const p = (n) => String(n).padStart(2, '0')
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  const s = String(ts)
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  if (m) return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`
  return s.length > 16 ? s.slice(0, 16) : s
}

export default function CandleChart({ bars = [] }) {
  const wrapRef = useRef(null)
  const [width, setWidth] = useState(760)

  useEffect(() => {
    const el = wrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width
      if (w) setWidth(Math.max(320, Math.round(w)))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const geom = useMemo(() => {
    if (!bars.length || width < 10) return null
    const W = width
    const priceTop = M.t
    const priceH = HEIGHT - M.t - M.b - VOL_H - GAP
    const plotW = W - M.l - M.r
    const step = plotW / bars.length
    const cw = Math.max(2, Math.min(16, step * 0.6))

    const highs = bars.map((b) => Number(b.high) || Number(b.close) || 0)
    const lows = bars.map((b) => Number(b.low) || Number(b.close) || 0)
    let max = Math.max(...highs)
    let min = Math.min(...lows)
    if (!Number.isFinite(max) || !Number.isFinite(min) || max === min) {
      max = min + 1
    }
    const pad = (max - min) * 0.08
    max += pad
    min -= pad
    const span = max - min || 1

    const x = (i) => M.l + (i + 0.5) * step
    const y = (p) => priceTop + ((max - p) / span) * priceH
    const volMax = Math.max(1, ...bars.map((b) => Number(b.volume) || 0))
    const volBase = priceTop + priceH + GAP + VOL_H
    const volH = (v) => (Math.max(0, Number(v) || 0) / volMax) * VOL_H

    const candles = bars.map((b, i) => {
      const o = Number(b.open) || Number(b.close) || 0
      const c = Number(b.close) || 0
      const hi = Number(b.high) || Math.max(o, c)
      const lo = Number(b.low) || Math.min(o, c)
      const up = c >= o
      const cx = x(i)
      const bodyTop = y(Math.max(o, c))
      const bodyBot = y(Math.min(o, c))
      return {
        key: i,
        cx,
        up,
        wickTop: y(hi),
        wickBot: y(lo),
        bodyTop,
        bodyH: Math.max(1, bodyBot - bodyTop),
        bodyX: cx - cw / 2,
        cw,
        vol: volH(b.volume),
        volY: volBase - volH(b.volume),
      }
    })

    const levels = [0, 1, 2, 3, 4].map((k) => {
      const p = min + (span * k) / 4
      return { p, y: y(p) }
    })

    const last = bars[bars.length - 1]
    const lastUp = Number(last.close) >= Number(last.open)
    return {
      W,
      priceTop,
      priceH,
      plotW,
      step,
      candles,
      levels,
      volBase,
      lastY: y(Number(last.close) || 0),
      lastClose: Number(last.close) || 0,
      lastUp,
      life: { first: timeLabel(bars[0].ts), mid: timeLabel(bars[Math.floor(bars.length / 2)].ts), last: timeLabel(last.ts) },
    }
  }, [bars, width])

  if (!geom) return <div className="chart-empty" ref={wrapRef}>暂无 K 线数据</div>

  const { W, candles, levels, volBase, lastY, lastClose, lastUp, life } = geom
  const plotRight = W - M.r

  return (
    <div className="chart-shell" ref={wrapRef}>
      <svg
        className="candle-chart"
        width={W}
        height={HEIGHT}
        viewBox={`0 0 ${W} ${HEIGHT}`}
        role="img"
        aria-label="K 线图"
      >
        <defs>
          <clipPath id="cq-plot">
            <rect x={M.l} y={M.t} width={plotRight - M.l} height={geom.priceH + (HEIGHT - geom.priceH - geom.priceTop - M.b)} />
          </clipPath>
        </defs>

        {levels.map((lv, i) => (
          <g key={i}>
            <line className="chart-grid" x1={M.l} x2={plotRight} y1={lv.y} y2={lv.y} />
            <text className="chart-axis" x={plotRight + 10} y={lv.y + 3.5}>
              {formatPrice(lv.p)}
            </text>
          </g>
        ))}

        <g clipPath="url(#cq-plot)">
          {candles.map((c) => (
            <g key={c.key} className={c.up ? 'candle-up' : 'candle-down'}>
              <line className="wick" x1={c.cx} x2={c.cx} y1={c.wickTop} y2={c.wickBot} />
              <rect className="body" x={c.bodyX} y={c.bodyTop} width={c.cw} height={c.bodyH} rx={c.cw > 5 ? 1 : 0} />
            </g>
          ))}
        </g>

        <line className="chart-vol-base" x1={M.l} x2={plotRight} y1={volBase} y2={volBase} />
        <g clipPath="url(#cq-plot)">
          {candles.map((c) => (
            <rect
              key={`v${c.key}`}
              className={c.up ? 'vol-up' : 'vol-down'}
              x={c.bodyX}
              y={c.volY}
              width={c.cw}
              height={Math.max(0.5, c.vol)}
              rx={c.cw > 5 ? 1 : 0}
            />
          ))}
        </g>

        <line
          className={`chart-last-line ${lastUp ? 'is-up' : 'is-down'}`}
          x1={M.l}
          x2={plotRight}
          y1={lastY}
          y2={lastY}
        />
        <rect className={`chart-last-tag ${lastUp ? 'is-up' : 'is-down'}`} x={plotRight + 4} y={lastY - 9} width={M.r - 10} height={18} rx={4} />
        <text className="chart-last-text" x={plotRight + 9} y={lastY + 4}>
          {formatPrice(lastClose)}
        </text>

        <text className="chart-axis" x={M.l} y={HEIGHT - 6}>{life.first}</text>
        <text className="chart-axis" x={M.l + (plotRight - M.l) / 2} y={HEIGHT - 6} textAnchor="middle">{life.mid}</text>
        <text className="chart-axis" x={plotRight} y={HEIGHT - 6} textAnchor="end">{life.last}</text>
      </svg>
    </div>
  )
}
