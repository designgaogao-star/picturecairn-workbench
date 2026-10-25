import type { ComponentChildren } from 'preact';
import { useLayoutEffect, useRef } from 'preact/hooks';
import { narrow } from '../state/app';

const panels: HTMLDialogElement[] = [];

/** Non-modal on a desktop; native focus containment and Escape on narrow screens. */
export function SidePanel({ class: className, label, onClose, children, desktopEscape = true, closeOnNarrow = false }: {
  class: string; label: string; onClose: () => void; children: ComponentChildren; desktopEscape?: boolean; closeOnNarrow?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const origin = useRef(document.activeElement as HTMLElement | null);
  const restoreOrigin = useRef(false);
  const close = useRef(onClose);
  close.current = onClose;
  const modal = narrow.value;
  const previousModal = useRef(modal);
  useLayoutEffect(() => {
    const element = ref.current!;
    const wasModal = previousModal.current;
    previousModal.current = modal;
    if (modal && !wasModal && closeOnNarrow) {
      close.current();
      return;
    }
    const focused = document.activeElement as HTMLElement | null;
    const within = focused && element.contains(focused);
    if (element.open) element.close();
    if (modal) element.showModal();
    else element.show();
    if (within) focused.focus({ preventScroll: true });
    else if (!modal) origin.current?.focus({ preventScroll: true });
    if (modal || desktopEscape) panels.push(element);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || element.closest('[inert]') || panels.at(-1) !== element || document.querySelector('dialog:modal')) return;
      event.preventDefault();
      close.current();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      const index = panels.indexOf(element);
      if (index >= 0) panels.splice(index, 1);
      const active = document.activeElement as HTMLElement | null;
      restoreOrigin.current = Boolean(active && element.contains(active));
      if (element.open) element.close();
      // Native dialog.close() can restore an old origin even when focus has moved to the wall.
      if (!restoreOrigin.current && active?.isConnected) active.focus({ preventScroll: true });
    };
  }, [modal, desktopEscape, closeOnNarrow]);
  useLayoutEffect(() => () => {
    if (restoreOrigin.current && origin.current?.isConnected) origin.current.focus({ preventScroll: true });
  }, []);
  return <dialog ref={ref} class={className} aria-label={label} aria-modal={modal ? 'true' : undefined}
    data-escape-panel={desktopEscape ? '' : undefined}
    onCancel={(event) => { event.preventDefault(); close.current(); }}
    onClick={(event) => {
      const element = ref.current;
      if (!modal || !element || event.target !== element) return;
      const rect = element.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right) close.current();
    }}>{children}</dialog>;
}
