/**
 * 全量备份导出 / 导入（前端 AES-GCM 加密，密码不经过服务器）
 *
 * 文件格式：{ mj_backup: 2, kdf: 'PBKDF2-SHA256', iter, salt(b64), iv(b64), data(b64) }
 *   v1 = 只有命局档案（旧文件，仍可导入）
 *   v2 = 档案 + 记录（含回收站）+ 校验台账与断言反馈
 *
 * 为什么必须做这件事：数据存在服务器上，用浏览器里的一枚令牌关联——
 * 清浏览器数据、换设备、无痕模式都会**失去关联**（数据还在，但认不回你名下）。
 * 导出是唯一的搬家与兜底手段，所以密码下限 8 位、密码不经过服务器。
 */
import { api, qs } from './client'

const PBKDF2_ITER = 150_000
const BACKUP_VERSION = 2

export interface ImportResult {
  profile: { id: string }
  records: number
  ledger: { logs: number; feedback: number }
}

/** 生成一枚强密码（4 组 5 位，去掉易混字符）：安全路径必须是省事的那条 */
export function suggestPassphrase(): string {
  const abc = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(20))
  const s = Array.from(bytes, (x) => abc[x % abc.length]).join('')
  return [s.slice(0, 5), s.slice(5, 10), s.slice(10, 15), s.slice(15, 20)].join('-')
}

function bufToB64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}

function b64ToBuf(b64: string): ArrayBuffer {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes.buffer
}

async function deriveKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: salt as unknown as BufferSource, iterations: PBKDF2_ITER, hash: 'SHA-256' },
    base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'],
  )
}

async function encryptJson(obj: unknown, passphrase: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt)
  const cipher = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(obj)))
  return JSON.stringify({
    mj_backup: BACKUP_VERSION,
    kdf: 'PBKDF2-SHA256',
    iter: PBKDF2_ITER,
    salt: bufToB64(salt.buffer as ArrayBuffer),
    iv: bufToB64(iv.buffer as ArrayBuffer),
    data: bufToB64(cipher),
  })
}

async function decryptJson(text: string, passphrase: string): Promise<Record<string, unknown>> {
  let env: { mj_backup?: number; kdf?: string; salt: string; iv: string; data: string }
  try {
    env = JSON.parse(text)
  } catch {
    throw new Error('这不是备份文件（内容不是 JSON）')
  }
  if ((env.mj_backup !== 1 && env.mj_backup !== 2) || env.kdf !== 'PBKDF2-SHA256') {
    throw new Error('不是本应用导出的备份文件')
  }
  const key = await deriveKey(passphrase, new Uint8Array(b64ToBuf(env.salt)))
  try {
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: new Uint8Array(b64ToBuf(env.iv)) }, key, b64ToBuf(env.data))
    return JSON.parse(new TextDecoder().decode(plain)) as Record<string, unknown>
  } catch {
    throw new Error('解密失败：密码错误或文件已损坏')
  }
}

function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** 导出：向服务端取明文全量数据 → 本地加密 → 下载 .mjson */
export async function exportBackup(passphrase: string, ownerId: string): Promise<string> {
  if (!passphrase || passphrase.length < 8) {
    // 至少 8 位：文件里有出生信息、全部卦例与手写的应验判定，而它会离开本机
    // （进网盘、微信、邮箱）。15 万次 PBKDF2 对 4 位数字没用——几分钟就能全试完。
    throw new Error('加密密码至少 8 位（短密码对拿到文件的人没有防护作用）')
  }
  let data: unknown
  try {
    data = await api.get(`/api/mingju/export${qs({ id: ownerId })}`)
  } catch (e) {
    if ((e as { status?: number }).status === 404) throw new Error('还没有命局档案，请先保存一份')
    throw new Error('导出失败：拿不到服务端数据')
  }
  const cipher = await encryptJson({ ...(data as object), mj_export_version: BACKUP_VERSION }, passphrase)
  const d = new Date()
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  const name = `mingju-backup-${stamp}.mjson`
  downloadText(name, cipher)
  return name
}

/** 导入：解密文件 → 交给服务端落库（只搬数据、不搬凭证） */
export async function importBackup(passphrase: string, file: File): Promise<ImportResult> {
  if (!passphrase) throw new Error('请输入加密密码')
  const text = await file.text()
  const data = await decryptJson(text, passphrase)
  if (!data || typeof data !== 'object' || !(data as { profile?: unknown }).profile) {
    throw new Error('备份文件内容不完整（缺少命局档案）')
  }
  const out = await api.post<ImportResult>('/api/mingju/import', { data })
  return {
    profile: out.profile,
    records: out.records ?? 0,
    ledger: out.ledger ?? { logs: 0, feedback: 0 },
  }
}
