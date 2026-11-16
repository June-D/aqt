import axios from 'axios'
import { mapTimeFields } from './utils/time'

const TOKEN_KEY = 'aqt_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

const http = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

http.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

http.interceptors.response.use(
  (r) => {
    if (r.data !== undefined) r.data = mapTimeFields(r.data)
    return r
  },
  (err) => {
    if (err.response?.status === 401) {
      const url = String(err.config?.url || '')
      if (!url.includes('/auth/login')) {
        setToken('')
        window.dispatchEvent(new Event('aqt-auth-lost'))
      }
    }
    const msg = err.response?.data?.detail || err.message
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  },
)

export const api = {
  authStatus: () => http.get('/auth/status').then((r) => r.data),
  login: (username, password) => http.post('/auth/login', { username, password }).then((r) => r.data),
  logout: () => http.post('/auth/logout').then((r) => r.data),
  status: () => http.get('/system/status').then((r) => r.data),
  control: (body) => http.post('/system/control', body).then((r) => r.data),
  reconcile: () => http.post('/system/reconcile').then((r) => r.data),
  account: () => http.get('/account').then((r) => r.data),
  positions: () => http.get('/positions').then((r) => r.data),
  orders: () => http.get('/orders').then((r) => r.data),
  placeOrder: (body) => http.post('/orders', body).then((r) => r.data),
  cancelOrder: (id) => http.post(`/orders/${id}/cancel`).then((r) => r.data),
  riskEvents: () => http.get('/risk/events').then((r) => r.data),
  riskAlerts: () => http.get('/risk-alerts').then((r) => r.data),
  statusBar: () => http.get('/system/status-bar').then((r) => r.data),
  getSettings: () => http.get('/settings').then((r) => r.data),
  putSettings: (body) => http.put('/settings', body).then((r) => r.data),
  accountOverview: () => http.get('/account/overview').then((r) => r.data),
  liquidate: (body) => http.post('/positions/liquidate', body).then((r) => r.data),
  symbolLedger: (symbol) => http.get(`/positions/${symbol}/ledger`).then((r) => r.data),
  marketQuotes: (symbols) => http.get('/market/quotes', { params: { symbols } }).then((r) => r.data),
  marketKline: (params) => http.get('/market/kline', { params }).then((r) => r.data),
  marketBoard: (params) => http.get('/market/board', { params }).then((r) => r.data),
  intelStatus: () => http.get('/intel/status').then((r) => r.data),
  intelToggle: (enabled) => http.post('/intel/toggle', { enabled }).then((r) => r.data),
  intelHotRefresh: () => http.post('/intel/hot-pool/refresh').then((r) => r.data),
  intelLlmGet: () => http.get('/intel/llm').then((r) => r.data),
  intelLlmSave: (body) => http.post('/intel/llm', body).then((r) => r.data),
  intelNews: () => http.get('/intel/news').then((r) => r.data),
  intelRuns: () => http.get('/intel/runs').then((r) => r.data),
  intelPredictions: () => http.get('/intel/predictions').then((r) => r.data),
}

export default http
