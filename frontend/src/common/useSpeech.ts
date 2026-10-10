import { useCallback, useEffect, useRef, useState } from 'react'
import { asrStatus, transcribe } from '../api/asr'

/**
 * 语音输入钩子：服务端识别优先，未配置或失败时回退浏览器自带识别。
 *
 * 为什么两套：
 *  · 服务端识别（阿里云百炼）中文准、跨浏览器一致，但要有密钥、按秒计费；
 *  · 浏览器自带识别（Chrome 走 Google 服务器，国内常被拦）不需要密钥，可作为兜底。
 * 不支持时**把原因讲清楚**（HTTPS、浏览器不支持、没设备、权限被拒），
 * 而不是让按钮点了没反应。
 */
export type SpeechState = 'idle' | 'recording' | 'uploading'

export interface SpeechApi {
  supported: boolean
  reason: string
  state: SpeechState
  error: string
  /** 浏览器识别过程中的临时文本（边说边出） */
  interim: string
  mode: 'server' | 'browser' | 'none'
  start: () => Promise<void>
  stop: () => void
  cancel: () => void
}

const SR = (): unknown => {
  const w = window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

export function useSpeech(onResult: (text: string) => void): SpeechApi {
  const [state, setState] = useState<SpeechState>('idle')
  const [error, setError] = useState('')
  const [interim, setInterim] = useState('')
  const [serverOk, setServerOk] = useState(false)
  const [checked, setChecked] = useState(false)

  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const srRef = useRef<{ start: () => void; stop: () => void; abort: () => void } | null>(null)

  useEffect(() => {
    asrStatus().then((s) => { setServerOk(!!s.configured); setChecked(true) }).catch(() => setChecked(true))
  }, [])

  const secure = (() => {
    try {
      const h = location.hostname
      return location.protocol === 'https:' || h === 'localhost' || h === '127.0.0.1' || h === '[::1]'
    } catch {
      return false
    }
  })()

  const hasRecorder = typeof window !== 'undefined' && typeof window.MediaRecorder !== 'undefined'
  const hasBrowserSr = !!SR()

  const mode: SpeechApi['mode'] = serverOk && hasRecorder ? 'server' : (hasBrowserSr ? 'browser' : 'none')

  const reason = !secure
    ? '语音需要 HTTPS 或 localhost 才能用（浏览器规定：http 站点不给麦克风）。'
    : !checked
      ? '正在检查语音识别可用性…'
      : mode === 'none'
        ? (hasRecorder
          ? '服务端语音识别未配置，且这个浏览器不支持自带识别（Firefox 两者都不支持）。'
          : '这个浏览器不支持录音（MediaRecorder），换 Chrome／Edge／Safari 试试。')
        : ''

  const supported = secure && checked && mode !== 'none'

  const cleanup = useCallback(() => {
    try { streamRef.current?.getTracks().forEach((t) => t.stop()) } catch { /* 忽略 */ }
    streamRef.current = null
    recRef.current = null
    chunksRef.current = []
  }, [])

  const start = useCallback(async () => {
    setError(''); setInterim('')
    if (!supported) { setError(reason || '当前环境不支持语音输入'); return }
    try {
      if (mode === 'server') {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        streamRef.current = stream
        const rec = new MediaRecorder(stream)
        chunksRef.current = []
        rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
        rec.onstop = async () => {
          cleanup()
          const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
          if (!blob.size) { setState('idle'); setError('没录到声音，再说一次？'); return }
          setState('uploading')
          try {
            const r = await transcribe(blob, 'speech.webm')
            if (r.text?.trim()) onResult(r.text.trim())
            else setError('没听清，再说一次？')
          } catch (e) {
            const status = (e as { status?: number }).status
            if (status === 503) { setError('服务端识别未配置；请改用支持语音识别的浏览器，或先在 backend/.env 配置 ASR_API_KEY。') }
            else if (status && status >= 500) setError('识别服务连不上或出错，稍后再试。')
            else setError((e as Error).message || '识别失败')
          } finally {
            setState('idle')
          }
        }
        rec.start()
        recRef.current = rec
        setState('recording')
        return
      }

      // 浏览器自带识别
      const Ctor = SR() as new () => {
        lang: string; continuous: boolean; interimResults: boolean
        onresult: ((e: { resultIndex: number; results: { length: number; [i: number]: { 0: { transcript: string }; isFinal: boolean } } }) => void) | null
        onerror: ((e: { error: string }) => void) | null
        onend: (() => void) | null
        start: () => void; stop: () => void; abort: () => void
      }
      const sr = new Ctor()
      sr.lang = 'zh-CN'
      sr.continuous = false
      sr.interimResults = true
      let finalText = ''
      sr.onresult = (e) => {
        let live = ''
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i]
          if (r.isFinal) finalText += r[0].transcript
          else live += r[0].transcript
        }
        setInterim(live)
      }
      sr.onerror = (e) => {
        const map: Record<string, string> = {
          'not-allowed': '麦克风被拦下了：请点地址栏左侧的权限图标允许麦克风。',
          'service-not-allowed': '这个浏览器不允许用语音识别服务。',
          'no-speech': '没听到声音。直接说，靠近一点麦克风。',
          network: '识别服务连不上（Chrome 的中文识别要走 Google 服务器，国内常被拦——换 Edge 或 Safari 一般就能用）。',
          aborted: '',
        }
        const msg = map[e.error] ?? `识别出错（${e.error}）。`
        if (msg) setError(msg)
      }
      sr.onend = () => {
        setState('idle')
        const t = finalText.trim()
        if (t) onResult(t)
        setInterim('')
      }
      srRef.current = sr
      sr.start()
      setState('recording')
    } catch (e) {
      cleanup()
      setState('idle')
      const name = (e as { name?: string }).name
      if (name === 'NotAllowedError') setError('麦克风被拦下了：请点地址栏左侧的权限图标允许麦克风。')
      else if (name === 'NotFoundError') setError('没检测到麦克风设备。')
      else setError(`打不开麦克风：${(e as Error).message || name || '未知原因'}`)
    }
  }, [supported, reason, mode, onResult, cleanup])

  const stop = useCallback(() => {
    if (mode === 'server') {
      try { recRef.current?.stop() } catch { cleanup(); setState('idle') }
    } else {
      try { srRef.current?.stop() } catch { setState('idle') }
    }
  }, [mode, cleanup])

  const cancel = useCallback(() => {
    try { recRef.current?.stop() } catch { /* 忽略 */ }
    try { srRef.current?.abort() } catch { /* 忽略 */ }
    cleanup()
    setState('idle')
    setInterim('')
  }, [cleanup])

  useEffect(() => () => { cleanup() }, [cleanup])

  return { supported, reason, state, error, interim, mode, start, stop, cancel }
}
