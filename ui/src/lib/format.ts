const NUMBER = new Intl.NumberFormat('zh-CN');

export const count = (value: number | null | undefined) => (value == null ? '—' : NUMBER.format(value));

export function bytes(value: number | null | undefined): string {
  if (value == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value, unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}

export const percent = (value: number) => `${(value * 100).toFixed(value >= 0.995 || value === 0 ? 0 : 1)}%`;

export function time(seconds: number | null | undefined): string {
  if (!seconds) return '—';
  const date = new Date(seconds * 1000);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return date.toLocaleString('zh-CN', sameDay ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
    : { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/** Backend errors quote paths the Python way ('C:\\dir\\file'); show them with single backslashes. */
export const readableError = (text: string) => text.replace(/'[^']*'/g, (quoted) => quoted.replace(/\\\\/g, '\\'));

/** Group names often start with a bracketed category, which is shown separately as a badge. */
export function stripCategory(name: string): string {
  return name.replace(/^\[(R16|R18|非R18)\]\s*/, '') || name;
}

export function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
}

/** Formats that may animate; metadata decides, this only drives the provisional state. */
export const mayAnimate = (name: string) => ['gif', 'webp', 'png', 'apng'].includes(extension(name));

/** Directory part of a package relative to its group, e.g. "第1季" for "作者/第1季/Vol.01". */
export function packageParent(packageRel: string, packageName: string, groupRel: string | undefined): string {
  let rel = packageRel;
  if (groupRel && rel.startsWith(groupRel + '/')) rel = rel.slice(groupRel.length + 1);
  else if (groupRel && rel === groupRel) rel = '';
  const parts = rel.split('/');
  if (parts[parts.length - 1] === packageName) parts.pop();
  return parts.join(' / ');
}
