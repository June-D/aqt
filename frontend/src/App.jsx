import { useEffect, useMemo, useState } from 'react'
import { Layout, Menu, Button, Tooltip } from 'antd'
import {
  AlertOutlined,
  LineChartOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Market from './pages/Market'
import Intel from './pages/Intel'
import Orders from './pages/Orders'
import RiskEvents from './pages/RiskEvents'
import Settings from './pages/Settings'
import Login from './pages/Login'
import StatusBar from './components/StatusBar'
import { api, getToken, setToken } from './api'

const { Header, Sider, Content } = Layout

const PAGE_META = {
  '/market': { title: '大盘', desc: '实时热点与分时走势' },
  '/intel': { title: '情报', desc: '新闻、预测与自动下单记录' },
  '/orders': { title: '订单', desc: '账户、持仓与委托执行' },
  '/risk': { title: '风控', desc: '风控拦截与告警推送' },
  '/settings': { title: '设置', desc: '交易模式、情报源与行情配置' },
}

const MENU_ITEMS = [
  {
    type: 'group',
    label: '市场',
    children: [
      { key: '/market', icon: <LineChartOutlined />, label: '大盘' },
      { key: '/intel', icon: <ThunderboltOutlined />, label: '情报' },
    ],
  },
  {
    type: 'group',
    label: '账户',
    children: [
      { key: '/orders', icon: <UnorderedListOutlined />, label: '订单' },
      { key: '/risk', icon: <AlertOutlined />, label: '风控' },
    ],
  },
  {
    type: 'group',
    label: '系统',
    children: [{ key: '/settings', icon: <SettingOutlined />, label: '设置' }],
  },
]

function Shell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [status, setStatus] = useState(null)
  const [loadingStatus, setLoadingStatus] = useState(true)

  const current = useMemo(
    () => PAGE_META[location.pathname] || PAGE_META['/orders'],
    [location.pathname],
  )

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const st = await api.statusBar()
        if (alive) setStatus(st)
      } catch {
        if (alive) setStatus(null)
      } finally {
        if (alive) setLoadingStatus(false)
      }
    }
    load()
    const t = setInterval(load, 15000)
    const onStatus = () => load()
    window.addEventListener('aqt-status-changed', onStatus)
    return () => {
      alive = false
      clearInterval(t)
      window.removeEventListener('aqt-status-changed', onStatus)
    }
  }, [location.pathname])

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const apply = () => setCollapsed(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  const logout = async () => {
    try {
      await api.logout()
    } catch {
      /* ignore */
    }
    setToken('')
    window.dispatchEvent(new Event('aqt-auth-lost'))
  }

  return (
    <Layout className="aqt-shell">
      <Sider
        className="aqt-sider"
        width={224}
        collapsedWidth={68}
        collapsible
        collapsed={collapsed}
        trigger={null}
      >
        <div className="aqt-brand">
          <div className="aqt-brand-mark">AQ</div>
          {!collapsed && (
            <div className="aqt-brand-copy">
              <div className="aqt-brand-title">AQT</div>
              <div className="aqt-brand-sub">情报交易台</div>
            </div>
          )}
        </div>
        <Menu
          className="aqt-menu"
          theme="light"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
        <div className="aqt-sider-foot">
          <span className="aqt-foot-dot" />
          {!collapsed && <span className="aqt-foot-text">本地执行台 · v0.1</span>}
        </div>
      </Sider>

      <Layout>
        <Header className="aqt-header">
          <div className="aqt-header-left">
            <Button
              type="text"
              aria-label={collapsed ? '展开菜单' : '收起菜单'}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((v) => !v)}
              className="aqt-icon-btn"
            />
            <div className="aqt-header-title">
              <h1>{current.title}</h1>
              <p>{current.desc}</p>
            </div>
          </div>
          <div className="aqt-header-right">
            <StatusBar status={status} loading={loadingStatus} />
            <span className="aqt-header-divider" />
            <Tooltip title="退出登录">
              <Button type="text" aria-label="退出" icon={<LogoutOutlined />} onClick={logout} className="aqt-icon-btn" />
            </Tooltip>
          </div>
        </Header>

        <Content className="aqt-content">
          <Routes>
            <Route path="/market" element={<Market />} />
            <Route path="/intel" element={<Intel />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/risk" element={<RiskEvents />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/orders" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  const [gate, setGate] = useState('loading')

  useEffect(() => {
    const boot = async () => {
      try {
        const s = await api.authStatus()
        if (!s.required) {
          setGate('ok')
          return
        }
        setGate(getToken() ? 'ok' : 'login')
      } catch {
        setGate(getToken() ? 'ok' : 'login')
      }
    }
    boot()
    const onLost = () => setGate('login')
    window.addEventListener('aqt-auth-lost', onLost)
    return () => window.removeEventListener('aqt-auth-lost', onLost)
  }, [])

  if (gate === 'loading') return null
  if (gate === 'login') {
    return <Login onOk={() => setGate('ok')} />
  }

  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  )
}
