import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { installOwnerHeader } from './api/owner'
import './styles/tokens.css'
import './styles/base.css'
import './styles/book.css'
import './styles/components.css'
import './styles/views.css'
import './styles/llm.css'

// 归属令牌：所有同源 /api 请求自动带 X-Owner-Token（必须在首屏请求之前装好）
installOwnerHeader()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
