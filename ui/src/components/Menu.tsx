import type { ComponentChildren } from 'preact';
import { useLayoutEffect, useRef, useState } from 'preact/hooks';
import { Icon, type IconName } from '../lib/icons';

const ITEMS = '[role^="menuitem"]:not(:disabled)';

/** Menu button. No scrim: a press outside, Tab or Escape closes it, and Escape is consumed so page shortcuts stay quiet. */
export function Menu({ label, icon = 'Ellipsis', text, class: className, children }: {
  label: string; icon?: IconName; text?: string; class?: string; children: ComponentChildren;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (!open) return;
    // Items folded away by the container queries have no boxes and are skipped.
    const items = () => [...(wrap.current?.querySelectorAll<HTMLElement>(`.menu ${ITEMS}`) ?? [])].filter((item) => item.getClientRects().length);
    items()[0]?.focus();
    const onPointer = (event: PointerEvent) => { if (!wrap.current?.contains(event.target as Node)) setOpen(false); };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
        return;
      }
      if (event.key === 'Tab') { setOpen(false); return; }
      if (!wrap.current?.contains(document.activeElement)) return;
      const list = items();
      const at = list.indexOf(document.activeElement as HTMLElement);
      let next = -1;
      if (event.key === 'ArrowDown') next = (at + 1) % list.length;
      else if (event.key === 'ArrowUp') next = at <= 0 ? list.length - 1 : at - 1;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = list.length - 1;
      if (next < 0 || !list.length) return;
      event.preventDefault();
      list[next].focus();
    };
    window.addEventListener('pointerdown', onPointer, true);
    window.addEventListener('keydown', onKey, true);
    return () => {
      window.removeEventListener('pointerdown', onPointer, true);
      window.removeEventListener('keydown', onKey, true);
    };
  }, [open]);
  const onPick = (event: MouseEvent) => {
    if (!(event.target as Element).closest(ITEMS)) return;
    setOpen(false);
    trigger.current?.focus();
  };
  return (
    <div class={['menu-wrap', className].filter(Boolean).join(' ')} ref={wrap}>
      <button ref={trigger} class={text ? 'btn subtle small' : 'icon-btn'} title={label} aria-label={label}
        aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name={icon} size={text ? 14 : 18} />{text && <span class="label-wide">{text}</span>}
      </button>
      {open && <div class="menu" role="menu" aria-label={label} onClick={onPick}>{children}</div>}
    </div>
  );
}
