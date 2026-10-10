import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * 错误边界：只坏这一块，不整页白屏。
 * 为什么必须有：任何一个子组件抛错，React 会卸载整棵树 —— 页面变成空白，
 * 用户既看不到导航也看不到错误，只能刷新。这里兜住并给两个出口（重试 / 刷新）。
 * 文案要点：说清"是这一块坏了，不是你的数据坏了"。
 */
interface Props {
  children: ReactNode
  label?: string
  onRetry?: () => void
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 控制台留痕便于排查；不弹窗、不打断用户
    console.error('[页面错误]', this.props.label || '', error, info.componentStack)
  }

  private retry = () => {
    this.setState({ error: null })
    this.props.onRetry?.()
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="notice notice-err" role="alert" style={{ marginTop: 16 }}>
        <b>出错了</b>
        <span className="n-body">
          这一块（{this.props.label || '页面'}）渲染出错，已单独停住，其余内容不受影响。
          你的记录与档案都在服务器上，没有损坏。
          <span className="n-hint">错误信息：{error.message || String(error)}</span>
          <span style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
            <button type="button" className="btn-outline" style={{ padding: '6px 16px' }} onClick={this.retry}>
              重 试
            </button>
            <button type="button" className="btn-outline" style={{ padding: '6px 16px' }}
              onClick={() => window.location.reload()}>
              刷新页面
            </button>
          </span>
        </span>
      </div>
    )
  }
}
