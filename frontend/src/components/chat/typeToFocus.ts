/**
 * "Just start typing": a printable key pressed while nothing editable or clickable has focus should go to
 * the message box, like ChatGPT. Pure so the rules are tested without a browser.
 */
const INTERACTIVE =
  'a,button,input,textarea,select,summary,[contenteditable=""],[contenteditable="true"],[role="button"],[role="menuitem"],[role="tab"],[role="option"],[tabindex]';

export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  isComposing?: boolean;
  defaultPrevented?: boolean;
  target: unknown;
}

export const shouldFocusInput = (event: KeyLike, dialogOpen = false): boolean => {
  if (event.defaultPrevented || event.isComposing || dialogOpen) return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  if (event.key.length !== 1) return false; // Enter, Tab, arrows, F-keys and so on
  const target = event.target as { closest?: (selector: string) => unknown } | null;
  if (target && typeof target.closest === 'function' && target.closest(INTERACTIVE)) return false;
  return true;
};
