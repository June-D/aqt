import { useState } from 'react'
import { Button, Form, Input, message } from 'antd'
import { api, setToken } from '../api'

export default function Login({ onOk }) {
  const [busy, setBusy] = useState(false)

  const submit = async (values) => {
    setBusy(true)
    try {
      const res = await api.login(values.username, values.password)
      setToken(res.token)
      message.success('已登录')
      onOk()
    } catch (e) {
      message.error(e.message || '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-shell">
        <aside className="login-aside">
          <div className="login-mark">AQ</div>
          <h1>AQT 执行台</h1>
          <p className="login-tagline">单用户量化控制台 · 研究、模拟与实盘自动化</p>
          <ul className="login-points">
            <li><span className="login-dot" />实时热点与 K 线走势</li>
            <li><span className="login-dot" />情报驱动的自动下单</li>
            <li><span className="login-dot" />风控闸门与告警推送</li>
          </ul>
          <p className="login-risk">LIVE 模式会动用真实资金，请确认风险后再开启。</p>
        </aside>

        <section className="login-form">
          <div className="login-form-head">
            <h2>登录</h2>
            <p>输入账号与密码进入控制台。</p>
          </div>
          <Form layout="vertical" onFinish={submit} requiredMark={false}>
            <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}>
              <Input autoComplete="username" autoFocus size="large" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password autoComplete="current-password" size="large" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={busy} block size="large">
              登录
            </Button>
          </Form>
        </section>
      </div>
    </div>
  )
}
