import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MicIcon } from '../art/icons'
import { useSpeech } from './useSpeech'

/**
 * 浮动语音钮（可拖动，位置记在本机）
 * 用法：点一下开始说话，再点一下结束并识别；识别出的文字交给 onText。
 * 为什么必须 portal 到 body：.page 上有 transform 动画，fixed 元素会被它当参照物而错位。
 */
const POS_KEY = 'bagua_mic_pos'

export default function FloatingMic({ onText, label = '语音' }: {
  onText: (text: string) => void
  label?: string
}) {
  const speech = useSpeech(onText)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const movedRef = useRef(0)
  const startRef = useRef({ x: 0, y: 0, px: 0, py: 0 })

  /* 位置：读本地记录；没有就放右下角 */
  useEffect(() => {
    let saved: { x: number; y: number } | null = null
    try {
      const raw = localStorage.getItem(POS_KEY)
      if (raw) saved = JSON.parse(raw)
    } catch { /* 忽略 */ }
    const w = window.innerWidth
    const h = window.innerHeight
    const def = { x: w - 84, y: h - 120 }
    const p = saved || def
    setPos({
      x: Math.min(Math.max(8, p.x), w - 64),
      y: Math.min(Math.max(8, p.y), h - 64),
    })
  }, [])

  /* 视口变化时夹回可视区 */
  useEffect(() => {
    const clamp = () => {
      setPos((p) => (p ? {
        x: Math.min(Math.max(8, p.x), window.innerWidth - 64),
        y: Math.min(Math.max(8, p.y), window.innerHeight - 64),
      } : p))
    }
    window.addEventListener('resize', clamp)
    window.addEventListener('orientationchange', clamp)
    return () => {
      window.removeEventListener('resize', clamp)
      window.removeEventListener('orientationchange', clamp)
    }
  }, [])

  const save = useCallback((p: { x: number; y: number }) => {
    try { localStorage.setItem(POS_KEY, JSON.stringify(p)) } catch { /* 忽略 */ }
  }, [])

  const onPointerDown = (e: React.PointerEvent) => {
    if (!pos) return
    movedRef.current = 0
    startRef.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y }
    setDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return
    const dx = e.clientX - startRef.current.x
    const dy = e.clientY - startRef.current.y
    movedRef.current = Math.max(movedRef.current, Math.hypot(dx, dy))
    if (movedRef.current > 6) {
      const p = {
        x: Math.min(Math.max(8, startRef.current.px + dx), window.innerWidth - 64),
        y: Math.min(Math.max(8, startRef.current.py + dy), window.innerHeight - 64),
      }
      setPos(p)
    }
  }

  const onPointerUp = () => {
    setDragging(false)
    if (movedRef.current > 6) { if (pos) save(pos); return }   // 只是拖动，不触发说话
    if (speech.state === 'recording') speech.stop()
    else if (speech.state === 'idle') void speech.start()
  }

  if (!pos) return null

  const recording = speech.state === 'recording'
  const uploading = speech.state === 'uploading'
  const tip = !speech.supported
    ? speech.reason
    : recording
      ? '在听…说完点一下结束'
      : uploading ? '正在识别…' : `点一下说话（${speech.mode === 'server' ? '服务端识别' : '浏览器识别'}）`

  return createPortal(
    <>
      <button
        type="button"
        className={`float-mic ${recording ? 'recording' : ''} ${uploading ? 'busy' : ''}`}
        style={{ left: pos.x, top: pos.y }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => setDragging(false)}
        title={tip}
        aria-label={label}
      >
        <MicIcon size={20} />
      </button>

      {(recording || uploading || speech.interim || speech.error || !speech.supported) && (
        <div className="float-mic-tip" role="status" aria-live="polite" aria-atomic="true"
          style={{ left: Math.min(Math.max(8, pos.x - 200), window.innerWidth - 216), top: Math.max(8, pos.y - 56) }}>
          {speech.error
            ? <span className="fm-err">{speech.error}</span>
            : speech.interim
              ? <span className="fm-live">{speech.interim}</span>
              : tip}
        </div>
      )}
    </>,
    document.body,
  )
}
