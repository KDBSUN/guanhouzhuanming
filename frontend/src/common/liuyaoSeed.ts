/**
 * 摇杆物理参数 → 三枚铜钱（确定性算法）
 * 与 backend/liuyao_engine.py 的 seed_from_params / coins_from_seed / line_from_coins 逐位一致
 * （都是 IEEE-754 double 运算，JS 与 Python 结果相同，后端代码里有交叉验证的说明）。
 *
 * 为什么要在前端也算一遍：松手的那一刻界面就要显示这三枚钱的正反与这一爻的爻型，
 * 不能等服务器回包；而两边算法一致，所以"前端显示的钱面"与"后端排出的爻"必然相同。
 * 1 = 背（阳面），0 = 字。
 */
function fract(v: number): number {
  return v - Math.floor(v)
}

export interface ThrowParams {
  x: number          // 释放点相对摇杆中心的 X 偏移（px）
  y: number          // 释放点相对摇杆中心的 Y 偏移（px）
  duration: number   // 拖拽总时长（毫秒）
  speed: number      // 拖拽平均速度（px/ms）
}

export const COIN_MULT = [2654435761.0, 4050300333.0, 1103515245.0]
export const COIN_SALT = [227018.53125, 99991.75, 31415.92653]

export function seedFromParams(x: number, y: number, duration: number, speed: number): number {
  const raw = x * 1000.0 + y * 100.0 + duration / 1000.0 + speed * 1000.0
  return fract(raw)
}

/** 三枚钱：各自用互质的倍率与盐值，使三背/三字（老阳/老阴）真的可能出现 */
export function coinsFromSeed(seed: number): number[] {
  const coins: number[] = []
  for (let i = 0; i < 3; i++) {
    const u = seed * COIN_MULT[i] + COIN_SALT[i]
    coins.push(fract(u) >= 0.5 ? 1 : 0)
  }
  return coins
}

export interface LineResult {
  yinYang: number    // 1 阳 / 0 阴
  type: string       // 老阳 / 少阴 / 少阳 / 老阴
  moving: boolean
  marker: string     // ○ 阳动 / × 阴动
}

/** 三枚钱 → 爻型：三背老阳(动)、两背少阴、一背少阳、三字老阴(动) */
export function lineFromCoins(coins: number[]): LineResult {
  const backs = coins.reduce((a, b) => a + b, 0)
  if (backs === 3) return { yinYang: 1, type: '老阳', moving: true, marker: '○' }
  if (backs === 2) return { yinYang: 0, type: '少阴', moving: false, marker: '×' }
  if (backs === 1) return { yinYang: 1, type: '少阳', moving: false, marker: '·' }
  return { yinYang: 0, type: '老阴', moving: true, marker: '×' }
}

/** 一次摇卦的完整结果（供界面立即显示） */
export function throwOf(p: ThrowParams) {
  const seed = seedFromParams(p.x, p.y, p.duration, p.speed)
  const coins = coinsFromSeed(seed)
  const line = lineFromCoins(coins)
  return { ...line, coins }
}

/** 爻位说法：初爻…上爻 */
export const YAO_POS = ['初爻', '二爻', '三爻', '四爻', '五爻', '上爻']
