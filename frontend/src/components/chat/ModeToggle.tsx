import React from 'react';
import { ArrowUp } from 'lucide-react';
import type { ChatMode } from '../../types';

interface ModeToggleProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  /** `sm` sits in the message box toolbar; `md` is the larger one on the welcome screen. */
  size?: 'sm' | 'md';
}

/**
 * One rounded "High" button then a green up arrow. Off (the default) answers in Low, straight from the language model; on, the next
 * questions are researched and verified (High). Click it again to go back to Low.
 */
export const ModeToggle: React.FC<ModeToggleProps> = ({ mode, onModeChange, size = 'sm' }) => {
  const high = mode === 'scholar';
  return (
    <button
      type="button"
      aria-pressed={high}
      aria-label="High mode"
      title={high ? 'High is on: researched and verified answers. Click to go back to Low.' : 'Turn on High for researched, verified answers (otherwise answers come straight from the language model)'}
      onClick={() => onModeChange(high ? 'sprint' : 'scholar')}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 ${
        size === 'md' ? 'h-9 px-5 text-sm' : 'h-7 px-3 text-[11px]'
      } ${
        high
          ? 'border-[#ff6600] bg-orange-50 text-orange-700 shadow-sm dark:bg-orange-500/15 dark:text-orange-300'
          : 'border-slate-200 bg-white text-slate-600 hover:border-orange-400 hover:text-orange-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300'
      }`}
    >
      High
      <ArrowUp
        aria-hidden="true"
        strokeWidth={3}
        className={`text-emerald-500 dark:text-emerald-400 ${size === 'md' ? 'h-4 w-4' : 'h-3.5 w-3.5'}`}
      />
    </button>
  );
};
