/** A 股价格/金额：保留 2 位小数，避免浮点脏尾数 */
export function formatPrice(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatMoney(value) {
  return formatPrice(value)
}
