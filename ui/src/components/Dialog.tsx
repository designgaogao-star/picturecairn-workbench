import type { ComponentChildren } from 'preact';
import { useLayoutEffect, useRef } from 'preact/hooks';
import { Icon } from '../lib/icons';

interface Props {
  title: string;
  onClose: () => void;
  children: ComponentChildren;
  footer?: ComponentChildren;
  wide?: boolean;
  /** While true, Escape and the close button are ignored (e.g. a request is being accepted). */
  locked?: boolean;
}

/** Modal built on <dialog>: it traps focus and owns the keyboard while open. */
export function Dialog({ title, onClose, children, footer, wide, locked }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const element = ref.current!;
    const origin = document.activeElement as HTMLElement | null;
    if (!element.open) element.showModal();
    return () => {
      if (element.open) element.close();
      if (origin?.isConnected) origin.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog ref={ref} class={`dialog ${wide ? 'wide' : ''}`} aria-label={title} aria-modal="true"
      onCancel={(event) => { event.preventDefault(); if (!locked) onClose(); }}>
      <header class="dialog-head">
        <h2>{title}</h2>
        <button class="icon-btn" title="关闭" disabled={locked} onClick={onClose}><Icon name="X" /></button>
      </header>
      <div class="dialog-body">{children}</div>
      {footer && <footer class="dialog-foot">{footer}</footer>}
    </dialog>
  );
}
