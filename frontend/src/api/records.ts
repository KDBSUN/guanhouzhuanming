/**
 * 记录（可回放的快照）
 * 定位：记录用于"回看/回放之前做过的东西"，点开跳回当时的界面。
 * 一次解读只留一条：卦一出来先存（保证盘不丢），AI 断完再按 id 把带断语的完整快照回填。
 */
import { api, qs } from './client'

export type RecordKind = 'meihua' | 'liuyao' | 'bazi'

export interface RecordRow {
  id: number
  kind: RecordKind
  title: string
  subtitle: string
  question: string
  note: string
  pinned: number
  created_at: string
  updated_at: string
  payload: Record<string, unknown>
  /** 后端附带的反馈统计（有断言时才有） */
  outcome?: { done?: number; total?: number } | null
}

export interface TrashRow extends RecordRow {
  deleted_at: string
  days_left: number
}

export const KIND_LABEL: Record<RecordKind, string> = {
  meihua: '梅花',
  liuyao: '六爻',
  bazi: '八字',
}

export const TRASH_DAYS = 30

export async function fetchRecords(kind = ''): Promise<RecordRow[]> {
  const res = await api.get<{ records: RecordRow[] }>(`/api/records${qs({ kind })}`)
  return res.records || []
}

export async function fetchRecord(id: number): Promise<RecordRow | null> {
  try {
    return await api.get<RecordRow>(`/api/records/detail${qs({ id })}`)
  } catch (e) {
    if ((e as { status?: number }).status === 404) return null
    throw e
  }
}

export async function saveRecord(input: {
  kind: RecordKind
  title?: string
  subtitle?: string
  question?: string
  payload?: Record<string, unknown>
}): Promise<RecordRow | null> {
  try {
    return await api.post<RecordRow>('/api/records', {
      kind: input.kind,
      title: input.title || '',
      subtitle: input.subtitle || '',
      question: input.question || '',
      payload: input.payload || {},
    })
  } catch {
    return null      // 存不上不该打断解卦
  }
}

export async function updateRecord(id: number, patch: {
  title?: string
  /** 副标题：六爻改判用神后要跟着更新（里面写着"用神X · 补Y"） */
  subtitle?: string
  note?: string
  pinned?: number
  payload?: Record<string, unknown>
}): Promise<boolean> {
  try {
    await api.patch('/api/records', { id, ...patch })
    return true
  } catch {
    return false
  }
}

export async function deleteRecord(id: number): Promise<boolean> {
  try {
    await api.del(`/api/records${qs({ id })}`)
    return true
  } catch {
    return false
  }
}

/* ---------- 最近删除（软删除，保留 30 天，逾期后端自动清理） ---------- */

export async function fetchTrash(): Promise<{ rows: TrashRow[]; days: number }> {
  try {
    const data = await api.get<{ records: TrashRow[]; trash_days?: number }>('/api/records/trash')
    return { rows: data.records || [], days: data.trash_days ?? TRASH_DAYS }
  } catch {
    return { rows: [], days: TRASH_DAYS }
  }
}

export async function restoreRecords(ids: number[]): Promise<number> {
  try {
    const data = await api.post<{ count?: number }>('/api/records/restore', { ids })
    return data.count ?? 0
  } catch {
    return 0
  }
}

export async function purgeRecord(id: number): Promise<boolean> {
  try {
    await api.del(`/api/records/purge${qs({ id })}`)
    return true
  } catch {
    return false
  }
}

export async function emptyTrash(): Promise<number> {
  try {
    const data = await api.post<{ purged?: number }>('/api/records/trash/empty')
    return data.purged ?? 0
  } catch {
    return 0
  }
}

/** 时间显示：2026-09-20T18:12:33 → 09-20 18:12 */
export function fmtTime(ts: string): string {
  return (ts || '').replace('T', ' ').slice(5, 16)
}

/** 记录里存的东西是否是一次梅花/六爻的卦（决定能不能回放） */
export function replayKindOf(row: RecordRow): 'meihua' | 'liuyao' | 'bazi' | null {
  if (row.kind === 'meihua' || row.kind === 'liuyao' || row.kind === 'bazi') return row.kind
  return null
}
