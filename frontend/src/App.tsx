import { useCallback, useEffect, useRef, useState } from 'react'
import HomeView from './views/HomeView'
import MeihuaView from './views/MeihuaView'
import LiuyaoView from './views/LiuyaoView'
import BaziView from './views/BaziView'
import QimenView from './views/QimenView'
import DaliurenView from './views/DaliurenView'
import { MenuIcon, CloseIcon } from './art/icons'
import { InkDefs } from './art/book'
import RecordsPage from './views/RecordsPage'
import TermsPage from './views/TermsPage'
import YizhiView from './views/YizhiView'
import FeedbackPage from './views/FeedbackPage'
import ApiSettingsView from './views/ApiSettingsView'
import OwnerTokenPanel from './common/OwnerTokenPanel'
import ErrorBoundary from './common/ErrorBoundary'
import './styles/navigation.css'

/* ============================================================
   易占 · 白金版 —— 应用壳（v0）
   哈希路由与现有前端同构（#/meihua 等），浏览器 ←→ 可用；
   记录回放/快照等状态在正式版接入。
   ============================================================ */

export type View = 'home' | 'meihua' | 'liuyao' | 'bazi' | 'qimen' | 'daliuren' | 'records' | 'terms' | 'yizhi' | 'feedback' | 'api'

const VIEWS: View[] = ['home', 'meihua', 'liuyao', 'bazi', 'qimen', 'daliuren', 'records', 'terms', 'yizhi', 'feedback', 'api']

/* 八字先校验命局，再选占法；首页与八字是直接入口，其余按用途收纳。 */
interface NavItem { view: View; label: string }
interface NavGroup { title: string; items: NavItem[] }

const NAV_PRIMARY: NavItem[] = [
  { view: 'home', label: '首页' },
  { view: 'bazi', label: '八字' },
]
const NAV_GROUPS: NavGroup[] = [
  { title: '占卜', items: [
    { view: 'meihua', label: '梅花易数' },
    { view: 'liuyao', label: '纳甲六爻' },
    { view: 'qimen', label: '奇门遁甲' },
    { view: 'daliuren', label: '大六壬' },
  ]},
  { title: '研读与探索', items: [
    { view: 'terms', label: '术语地图' },
    { view: 'yizhi', label: '移植行星' },
  ]},
  { title: '我的与设置', items: [
    { view: 'records', label: '我的记录' },
    { view: 'api', label: 'API 设置' },
    { view: 'feedback', label: '公测反馈' },
  ]},
]

/** 全部入口共用此顺序，首页 → 八字 → 占卜 → 研读与探索 → 我的与设置。 */
const NAV_ITEMS: NavItem[] = [...NAV_PRIMARY, ...NAV_GROUPS.flatMap((g) => g.items)]

export const hashOf = (v: View) => `#/${v}`

function parseHash(): View {
  const h = window.location.hash.replace(/^#\/?/, '').split('?')[0].trim()
  return (VIEWS as string[]).includes(h) ? (h as View) : 'home'
}

const PAGE_TITLE = '观候·转明'

/* ---------- 顶部导航 ---------- */

function TopNav({ view }: { view: View }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const navRef = useRef<HTMLElement>(null)
  const burgerRef = useRef<HTMLButtonElement>(null)
  const closeMenus = useCallback(() => {
    setMenuOpen(false)
    setOpenGroup(null)
  }, [])

  useEffect(() => { closeMenus() }, [view, closeMenus])
  useEffect(() => {
    const onOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !navRef.current?.contains(event.target)) closeMenus()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (openGroup) {
        const opener = navRef.current?.querySelector<HTMLButtonElement>(`[data-nav-group="${openGroup}"]`)
        if (opener && navRef.current?.contains(document.activeElement)) opener.focus()
      } else if (menuOpen && navRef.current?.contains(document.activeElement)) {
        burgerRef.current?.focus()
      }
      closeMenus()
    }
    window.addEventListener('pointerdown', onOutside)
    window.addEventListener('keydown', onKey)
    window.addEventListener('hashchange', closeMenus)
    return () => {
      window.removeEventListener('pointerdown', onOutside)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('hashchange', closeMenus)
    }
  }, [closeMenus, menuOpen, openGroup])

  const navLink = (n: NavItem, desktop = false, inMenu = false) => (
    <a key={n.view}
      className={`${desktop ? 'topnav-tab ' : ''}${n.view === 'bazi' ? 'topnav-bazi ' : ''}${view === n.view ? 'active' : ''}`}
      href={hashOf(n.view)} aria-current={view === n.view ? 'page' : undefined}
      role={inMenu ? 'menuitem' : undefined}
      onClick={closeMenus}>
      {n.label}{n.view === 'bazi' && <small>命局先行</small>}
    </a>
  )

  /** 分组菜单内的方向键导航（menu 模式），Escape 交由全局 keydown 处理 */
  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLAnchorElement>('a[role="menuitem"]'))
    if (items.length === 0) return
    const idx = items.indexOf(document.activeElement as HTMLAnchorElement)
    const next = event.key === 'ArrowDown' ? (idx + 1) % items.length : (idx - 1 + items.length) % items.length
    event.preventDefault()
    items[next]?.focus()
  }

  /** 分组按钮上的方向键：ArrowDown/ArrowUp 打开菜单并聚焦首/末项（menu-button 模式） */
  const openDirRef = useRef<'first' | 'last' | null>(null)
  const onGroupKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, title: string) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    openDirRef.current = event.key === 'ArrowDown' ? 'first' : 'last'
    if (openGroup !== title) {
      setOpenGroup(title)
      return
    }
    // 菜单已打开：直接移动焦点
    openDirRef.current = null
    const menu = navRef.current?.querySelector<HTMLDivElement>(`#nav-menu-${title}`)
    const items = menu ? Array.from(menu.querySelectorAll<HTMLAnchorElement>('a[role="menuitem"]')) : []
    if (items.length === 0) return
    ;(event.key === 'ArrowDown' ? items[0] : items[items.length - 1]).focus()
  }

  /* 菜单挂载完成后，按打开方向聚焦首/末项（点击打开时不动焦点） */
  useEffect(() => {
    if (!openGroup || openDirRef.current == null) return
    const dir = openDirRef.current
    openDirRef.current = null
    const menu = navRef.current?.querySelector<HTMLDivElement>(`#nav-menu-${openGroup}`)
    const items = menu ? Array.from(menu.querySelectorAll<HTMLAnchorElement>('a[role="menuitem"]')) : []
    if (items.length === 0) return
    ;(dir === 'first' ? items[0] : items[items.length - 1]).focus()
  }, [openGroup])

  return (
    <nav ref={navRef} className={`topnav topnav-grouped ${menuOpen ? 'open' : ''}`} aria-label="主导航">
      <a className="topnav-brand" href={hashOf('home')} aria-label="观候·转明 · 返回首页" onClick={closeMenus}>
        <span className="brand-seal">观</span>
        <span className="brand-name">观候·转明</span>
        <span className="brand-slogan">观天机 · 断人事</span>
      </a>
      <div className="topnav-tabs">
        {NAV_PRIMARY.map((n) => navLink(n, true))}
        {NAV_GROUPS.map((g) => {
          const open = openGroup === g.title
          const selected = g.items.some((n) => n.view === view)
          return (
            <div key={g.title} className={`topnav-group${open ? ' open' : ''}${selected ? ' selected' : ''}`}>
              <button
                type="button"
                data-nav-group={g.title}
                className="topnav-tab"
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={`nav-menu-${g.title}`}
                aria-label={selected ? `${g.title}，当前分组` : g.title}
                onClick={() => setOpenGroup(open ? null : g.title)}
                onKeyDown={(e) => onGroupKeyDown(e, g.title)}
              >
                {g.title}<span className="nav-caret" aria-hidden="true">▾</span>
              </button>
              {open && (
                <div id={`nav-menu-${g.title}`} className="topnav-group-menu" role="menu"
                  aria-label={g.title} onKeyDown={onMenuKeyDown}>
                  {g.items.map((n) => navLink(n, false, true))}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <button ref={burgerRef} type="button" className="topnav-burger"
        aria-expanded={menuOpen} aria-controls="main-navigation-drawer"
        aria-label={menuOpen ? '收起导航' : '展开导航'}
        onClick={() => setMenuOpen((v) => !v)}>
        {menuOpen ? <CloseIcon size={18} /> : <MenuIcon size={18} />}
      </button>
      <div id="main-navigation-drawer" className="topnav-drawer">
        <div className="topnav-drawer-group">{NAV_PRIMARY.map((n) => navLink(n))}</div>
        {NAV_GROUPS.map((g) => (
          <div className={`topnav-drawer-group ${g.items.some((n) => n.view === view) ? 'selected' : ''}`} key={g.title}>
            <span className="topnav-drawer-title">{g.title}</span>
            {g.items.map((n) => navLink(n))}
          </div>
        ))}
      </div>
    </nav>
  )
}

/* ---------- 页脚 ---------- */

function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-cols">
          <div>
            <div className="footer-head">观候·转明</div>
            <p className="footer-text">
              以传统术数典籍为规则底本的行动辅助工具：卦象给方向，八字画边界，
              每一条建议都可回溯到原文。
            </p>
          </div>
          <div>
            <div className="footer-head">功能入口</div>
            <div className="footer-links">
              {NAV_ITEMS.map((n) => (
                <a key={n.view} className="footer-link" href={hashOf(n.view)}>{n.label}</a>
              ))}
            </div>
          </div>
          <div>
            <div className="footer-head">使用指南</div>
            <p className="footer-text">
              一事一占：一次只问一件具体的事<br />
              起卦前静心片刻，默念所问<br />
              建议先过命局校验，红线处自动改方
            </p>
          </div>
        </div>
        <div className="footer-caution">
          <b>郑重提示</b>
          请不要迷信。本站所有功能只是用程序的方式展示传统的占卜行为，没有神力，
          也不会替你做任何决定。如果您遇到难题，请通过社会途径寻求帮助——比如向专业人士咨询，
          或倾听朋友、长辈、领导的意见建议。此处不能给您实质性帮助，所涉内容亦未经现代科学验证，请悉知。
        </div>
        <OwnerTokenPanel />
        <p className="footer-note">每条判定都标了典籍出处，点一下即可展开原文核对</p>
        <p className="footer-disclaimer">
          以上为传统术数典籍的架构性整理，仅作文化研究与产品设计参考，不构成投资、医疗或法律建议；
          请不要迷信，遇到难题请通过社会途径寻求帮助。相关内容未经现代科学验证，请自行判断并承担相应责任。
        </p>
      </div>
    </footer>
  )
}

/* ---------- App ---------- */

export default function App() {
  const [view, setView] = useState<View>(parseHash)
  /** 首页写下的事带到起卦页：seed 变化时起卦页重挂载并预填问句 */
  const [seed, setSeed] = useState('')
  /** seed 是带给哪一页的：从导航（<a href>）进页面时不该残留上一句问句 */
  const seedViewRef = useRef<View | null>(null)
  /** 记录回放：把当时存的快照交给对应页面还原（不重新起卦、不产生新记录）。
      id 一并带上：回放页若要补跑「AI 解卦」，得知道断语回填到哪条记录。 */
  const [replay, setReplay] = useState<{ kind: View; payload: Record<string, unknown>; id?: number; n: number } | null>(null)

  useEffect(() => {
    const onHash = () => {
      const v = parseHash()
      if (seedViewRef.current !== null && seedViewRef.current !== v) {
        setSeed('')
        seedViewRef.current = null
      }
      setView(v)
      // 顶部导航是 <a href="#/…"> 直跳 hash，不走 go()；这里统一回顶部，
      // 否则在首页滚到底后点别的页会停在底部（2026-10 修）
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.title = PAGE_TITLE
  }, [view])

  /** 第二个参数是"从首页带过去的问句"；不传就清空，避免上一句残留 */
  const go = useCallback((v: View, q?: string) => {
    const text = q ?? ''
    setSeed(text)
    seedViewRef.current = text ? v : null
    setReplay(null)
    window.location.hash = `/${v}`
    window.scrollTo({ top: 0 })
  }, [])

  /** 记录页点「回放」：带着快照跳到当时的界面 */
  const replayRecord = useCallback((kind: string, payload: Record<string, unknown>, id?: number) => {
    const v = (kind === 'meihua' || kind === 'liuyao' || kind === 'bazi') ? kind : 'meihua'
    setSeed('')
    seedViewRef.current = null
    setReplay({ kind: v, payload, id, n: Date.now() })
    window.location.hash = `/${v}`
    window.scrollTo({ top: 0 })
  }, [])

  const rp = (v: View) => (replay?.kind === v ? replay.payload : null)
  const rk = (v: View) => (replay?.kind === v ? replay.n : '')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <InkDefs />
      <TopNav view={view} />
      {view === 'home' && <main className="page page-wide"><HomeView onGo={go} /></main>}
      {view === 'meihua' && (
        <main className="page" key={`meihua-${seed}-${rk('meihua')}`}>
          <ErrorBoundary label="梅花易数">
            <MeihuaView initialQuestion={seed} replay={rp('meihua')}
              replayId={replay?.kind === 'meihua' ? replay.id ?? null : null} />
          </ErrorBoundary>
        </main>
      )}
      {view === 'liuyao' && (
        <main className="page" key={`liuyao-${seed}-${rk('liuyao')}`}>
          <ErrorBoundary label="纳甲六爻">
            <LiuyaoView initialQuestion={seed} replay={rp('liuyao')} />
          </ErrorBoundary>
        </main>
      )}
      {view === 'bazi' && (
        <main className="page" key={`bazi-${rk('bazi')}`}>
          <ErrorBoundary label="四柱八字"><BaziView replay={rp('bazi')} /></ErrorBoundary>
        </main>
      )}
      {view === 'qimen' && (
        <main className="page" key="qimen">
          <ErrorBoundary label="奇门遁甲"><QimenView /></ErrorBoundary>
        </main>
      )}
      {view === 'daliuren' && (
        <main className="page" key="daliuren">
          <ErrorBoundary label="大六壬"><DaliurenView /></ErrorBoundary>
        </main>
      )}
      {view === 'records' && (
        <main className="page" key="records">
          <ErrorBoundary label="我的记录"><RecordsPage onReplay={replayRecord} /></ErrorBoundary>
        </main>
      )}
      {view === 'terms' && (
        <main className="page" key="terms">
          <ErrorBoundary label="术语地图"><TermsPage /></ErrorBoundary>
        </main>
      )}
      {view === 'yizhi' && (
        <main className="page" key="yizhi">
          <ErrorBoundary label="移植行星"><YizhiView /></ErrorBoundary>
        </main>
      )}
      {view === 'feedback' && (
        <main className="page" key={`feedback-${window.location.hash}`}>
          <ErrorBoundary label="公测反馈"><FeedbackPage /></ErrorBoundary>
        </main>
      )}
      {view === 'api' && (
        <main className="page" key="api">
          <ErrorBoundary label="API 设置"><ApiSettingsView /></ErrorBoundary>
        </main>
      )}
      <Footer />
    </div>
  )
}
