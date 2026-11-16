/** 后端存的是 UTC naive；界面统一显示北京时间 YYYY-MM-DD HH:mm:ss */
export function formatTime(value) {
  if (value == null || value === '') return '-'
  const d = toUtcDate(value)
  if (!d) return String(value)
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const g = (t) => parts.find((p) => p.type === t)?.value || '00'
  return `${g('year')}-${g('month')}-${g('day')} ${g('hour')}:${g('minute')}:${g('second')}`
}

function toUtcDate(value) {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }
  if (typeof value === 'number') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? null : d
  }
  const s = String(value).trim()
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/)
  if (m) {
    const iso = `${m[1]}T${m[2]}${m[3] || ''}${m[4] || 'Z'}`
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? null : d
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** 递归把 *_at / as_of 转成北京时间（API 响应用） */
export function mapTimeFields(data) {
  if (Array.isArray(data)) return data.map(mapTimeFields)
  if (data && typeof data === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(data)) {
      const isTs = /(_at|^as_of)$/.test(k) && (typeof v === 'string' || typeof v === 'number')
      out[k] = isTs ? formatTime(v) : mapTimeFields(v)
    }
    return out
  }
  return data
}
