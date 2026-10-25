/**
 * Text fields and modal dialogs own the keyboard: global shortcuts ignore their events.
 * Returns true when a shortcut handler should leave the event alone.
 */
export function keyboardOwnedElsewhere(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.isComposing) return true;
  const target = event.target as HTMLElement | null;
  if (target && (target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))) return true;
  if (event.key === 'Escape' && [...document.querySelectorAll('dialog[open][data-escape-panel]')]
    .some((panel) => !panel.closest('[inert]'))) return true;
  return Boolean(target?.closest('dialog[open]')) || document.querySelector('dialog:modal') !== null;
}

/** Modifier-free key press (Shift allowed only when `shift` is set). */
export function plainKey(event: KeyboardEvent, shift = false): boolean {
  return !event.ctrlKey && !event.metaKey && !event.altKey && (shift || !event.shiftKey);
}
