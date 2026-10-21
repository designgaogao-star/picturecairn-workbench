import type { JSX } from 'preact';
import {
  ArrowLeft, ArrowLeftRight, ArrowUp, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Circle, CircleAlert,
  Copy, CopyCheck, Dices, ExternalLink, FileText, Files, Flag, Folder, FolderOpen, FolderPlus, GitCompare, History, Image, Images, Info,
  LayoutGrid, ListChecks, LoaderCircle, Maximize, Menu, Minimize, Package, PanelBottom, Pause, Play, RefreshCw, RotateCcw,
  RotateCw, Scan, ScanSearch, ShieldAlert, Sparkles, Trash2, TriangleAlert, WifiOff, X, ZoomIn, ZoomOut,
  type IconNode,
} from 'lucide';

const icons = {
  ArrowLeft, ArrowLeftRight, ArrowUp, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Circle, CircleAlert,
  Copy, CopyCheck, Dices, ExternalLink, FileText, Files, Flag, Folder, FolderOpen, FolderPlus, GitCompare, History, Image, Images, Info,
  LayoutGrid, ListChecks, LoaderCircle, Maximize, Menu, Minimize, Package, PanelBottom, Pause, Play, RefreshCw, RotateCcw,
  RotateCw, Scan, ScanSearch, ShieldAlert, Sparkles, Trash2, TriangleAlert, WifiOff, X, ZoomIn, ZoomOut,
} satisfies Record<string, IconNode>;

export type IconName = keyof typeof icons;

export function Icon({ name, size = 18, class: className, spin }: { name: IconName; size?: number; class?: string; spin?: boolean }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width={2} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
      class={['icon', spin ? 'spin' : '', className].filter(Boolean).join(' ')}>
      {icons[name].map(([tag, attrs], i) => {
        const Tag = tag as keyof JSX.IntrinsicElements;
        return <Tag key={i} {...(attrs as Record<string, string>)} />;
      })}
    </svg>
  );
}
