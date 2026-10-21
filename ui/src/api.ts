import { GalleryClient, GalleryError } from '../../contracts/client';
import type { components } from '../../contracts/schema';
import { readableError } from './lib/format';

type S = components['schemas'];
export type Library = S['Library'];
export type Group = S['Group'];
export type Package = S['Package'];
export type ImageItem = S['ImageItem'];
export type ImageContext = S['ImageContext'];
export type Directory = S['Directory'];
export type Review = S['Review'];
export type Task = S['Task'];
export type Mark = Review['state'];
export type Edge = S['Edge'];
export type Pair = S['Pair'];
export type Operation = S['Operation'];
export type DeleteTarget = S['DeleteTarget'];
export type DeleteItem = S['DeleteItem'];
export type DeleteResult = S['DeleteResult'];
export type AnalyzeResult = S['AnalyzeResult'];
export type CompareResult = S['CompareResult'];
export type ComparedFile = S['ComparedFile'];
export type AuditResult = S['AuditResult'];
export type ShellPackage = S['ShellPackage'];
export type AuditPackage = S['AuditPackage'];
export type AuditImage = S['AuditImage'];
export type IncompletePackage = S['IncompletePackage'];
export type PackageSimilarity = S['PackageSimilarity'];
export type ScanResult = S['ScanResult'];
export type JobBody = S['ScanJob'] | S['HashJob'] | S['PrewarmJob'] | S['CompareJob'] | S['CollectJob'];
export interface Page<T> { items: T[]; total: number; offset: number; limit: number; revision: number }

/** Dev-only guard for exercising a catalog copy without submitting writes or background work. */
export const readonly = import.meta.env.DEV && new URLSearchParams(location.search).has('readonly');

export const client = new GalleryClient('', (input, options) => {
  const method = options?.method || (input instanceof Request ? input.method : 'GET');
  if (readonly && method.toUpperCase() !== 'GET') return Promise.reject(new Error('只读联调模式'));
  return fetch(input, options);
});
export { GalleryError };

export const EDGES: Edge[] = [400, 800, 1600, 2560, 4200];

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function statusOf(error: unknown): number | null {
  return error instanceof GalleryError ? error.status : null;
}

function detailText(detail: unknown): string | null {
  if (!detail || typeof detail !== 'object') return null;
  const record = detail as { error?: unknown; detail?: unknown };
  if (typeof record.error === 'string') return readableError(record.error);
  if (typeof record.detail === 'string') return readableError(record.detail);
  if (Array.isArray(record.detail)) return record.detail.map((item) => item?.msg).filter(Boolean).join('；') || null;
  return null;
}

const STATUS_TEXT: Record<number, string> = {
  403: '请求被后端拒绝（来源或主机不允许）',
  404: '资源已不存在',
  409: '状态冲突或文件已变化',
  413: '请求或图片过大，无法处理',
  422: '请求或图片无法处理',
  // 502/504 come from the dev server's proxy when the backend is down or stuck.
  502: '无法连接图库服务',
  503: '后台队列已满或服务正在停止，请稍后重试',
  504: '图库服务响应超时',
};

/** Human-readable Chinese description; the backend detail is kept for diagnosis. */
export function describeError(error: unknown): string {
  if (error instanceof GalleryError) {
    const base = STATUS_TEXT[error.status] || `请求失败（${error.status}）`;
    const detail = detailText(error.detail);
    return detail ? `${base}：${detail}` : base;
  }
  if (error instanceof TypeError) return '无法连接图库服务';
  if (error instanceof Error) return error.message;
  return String(error);
}

/** Smallest preview edge that still covers `needed` device pixels. */
export function pickEdge(needed: number): Edge {
  return EDGES.find((edge) => edge >= needed) || 4200;
}

export function thumbnailUrl(id: string, edge: Edge = 400): string { return client.thumbnail(id, edge); }
export function originalUrl(id: string): string { return client.original(id); }

export const ACTIVE_STATES: Task['state'][] = ['queued', 'running', 'paused', 'cancelling'];
export const isActive = (task: Pick<Task, 'state'>) => ACTIVE_STATES.includes(task.state);
