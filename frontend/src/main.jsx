import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1f4b43',
          colorInfo: '#1f4b43',
          colorSuccess: '#1f6b45',
          colorWarning: '#a33b1a',
          colorError: '#a33b1a',
          colorLink: '#1f4b43',
          colorBgBase: '#f3f4f6',
          colorBgLayout: '#f3f4f6',
          colorBgContainer: '#ffffff',
          colorBorder: '#e2e5ea',
          colorBorderSecondary: '#e2e5ea',
          colorText: '#15171e',
          colorTextSecondary: '#565d6b',
          colorTextTertiary: '#8a919f',
          borderRadius: 10,
          borderRadiusLG: 14,
          borderRadiusSM: 8,
          fontFamily: '"Sora", "PingFang SC", "Helvetica Neue", sans-serif',
          fontFamilyCode: '"JetBrains Mono", ui-monospace, monospace',
          controlHeight: 36,
          boxShadow: '0 1px 2px rgba(21, 23, 30, 0.04)',
          boxShadowSecondary: '0 1px 2px rgba(21, 23, 30, 0.04), 0 16px 36px rgba(21, 23, 30, 0.10)',
          motionDurationMid: '0.16s',
        },
        components: {
          Layout: {
            bodyBg: '#f3f4f6',
            headerBg: '#ffffff',
            siderBg: '#ffffff',
          },
          Menu: {
            itemBg: 'transparent',
            itemColor: '#565d6b',
            itemSelectedColor: '#1f4b43',
            itemSelectedBg: '#e7f0ed',
            itemHoverColor: '#15171e',
            itemHoverBg: '#f3f4f6',
            itemHeight: 40,
            itemBorderRadius: 8,
            groupTitleColor: '#8a919f',
            groupTitleFontSize: 11,
            iconSize: 15,
          },
          Table: {
            headerBg: '#fafafb',
            headerColor: '#565d6b',
            rowHoverBg: '#f5f7f6',
            borderColor: '#e2e5ea',
            cellPaddingBlock: 12,
            cellPaddingInline: 16,
            headerSplitColor: 'transparent',
          },
          Button: { primaryShadow: 'none', defaultShadow: 'none', fontWeight: 550 },
          Input: { activeBorderColor: '#1f4b43', hoverBorderColor: '#cfd4dd', activeShadow: '0 0 0 3px rgba(31, 75, 67, 0.14)' },
          InputNumber: { activeBorderColor: '#1f4b43', hoverBorderColor: '#cfd4dd' },
          Select: { optionSelectedBg: '#e7f0ed' },
          Switch: { colorPrimary: '#1f4b43' },
          Pagination: { itemActiveBg: '#e7f0ed' },
          Tooltip: { colorBgSpotlight: '#15171e', borderRadius: 8 },
          Modal: { borderRadiusLG: 14 },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
