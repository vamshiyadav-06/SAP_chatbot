import { describe, expect, it } from 'vitest';
import { shouldFocusInput } from './typeToFocus';

const plain = { closest: () => null };
const key = (over: Partial<Parameters<typeof shouldFocusInput>[0]> = {}) => ({
  key: 'a', ctrlKey: false, metaKey: false, altKey: false, target: plain, ...over,
});

describe('shouldFocusInput', () => {
  it('sends a printable key pressed on the page to the message box', () => {
    expect(shouldFocusInput(key())).toBe(true);
    expect(shouldFocusInput(key({ key: ' ' }))).toBe(true);
  });
  it('leaves shortcuts, special keys and IME composition alone', () => {
    expect(shouldFocusInput(key({ ctrlKey: true }))).toBe(false);
    expect(shouldFocusInput(key({ metaKey: true }))).toBe(false);
    expect(shouldFocusInput(key({ key: 'Enter' }))).toBe(false);
    expect(shouldFocusInput(key({ key: 'ArrowDown' }))).toBe(false);
    expect(shouldFocusInput(key({ isComposing: true }))).toBe(false);
  });
  it('never steals keys from fields, buttons or links', () => {
    expect(shouldFocusInput(key({ target: { closest: () => ({}) } }))).toBe(false);
  });
  it('does nothing while a dialog is open', () => {
    expect(shouldFocusInput(key(), true)).toBe(false);
  });
});
