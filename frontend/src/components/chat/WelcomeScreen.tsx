import React from 'react';
import { ArrowRight, ShieldAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import iconOnly from '../../assets/clyptusap-icon.png';
import type { ChatMode } from '../../types';
import { MODES, SUGGESTIONS } from './welcomeContent';
import { ModeToggle } from './ModeToggle';

interface WelcomeScreenProps {
  onSelectPrompt: (prompt: string) => void;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onSelectPrompt, mode, onModeChange }) => {
  return (
    <div className="chat-welcome mx-auto w-full max-w-2xl px-4 py-6 text-center">
      <motion.div
        className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 bg-white p-2 shadow-sm dark:border-slate-800 dark:bg-slate-950"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
      >
        <img src={iconOnly} alt="" className="h-full w-full object-contain" />
      </motion.div>

      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
        SAP BRIM knowledge assistant
      </p>
      <h1 className="pt-1.5 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
        Welcome to Clyptus AI
      </h1>
      <p className="mx-auto max-w-md pt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
        Ask about SAP and SAP BRIM: configuration, transactions, processes and troubleshooting.
      </p>

      <div className="mt-5 flex flex-col items-center gap-2">
        <ModeToggle mode={mode} onModeChange={onModeChange} size="md" />
        <p className="max-w-sm text-xs leading-snug text-slate-600 dark:text-slate-400" aria-live="polite">
          {MODES.find((m) => m.id === mode)?.detail}
        </p>
      </div>

      <p className="mx-auto mb-2 max-w-xl pt-6 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
        Try a {mode === 'sprint' ? 'quick' : 'research'} question
      </p>
      <div className="mx-auto grid max-w-xl grid-cols-1 gap-2 text-left sm:grid-cols-2" key={mode}>
        {SUGGESTIONS[mode].map(({ icon: Icon, title, description, prompt }, index) => (
          <motion.button
            key={title}
            type="button"
            onClick={() => onSelectPrompt(prompt)}
            title={prompt}
            className="group flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-orange-500/40 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04, duration: 0.2 }}
          >
            <span className="shrink-0 rounded-lg bg-slate-100 p-1.5 text-slate-600 transition group-hover:text-orange-600 dark:bg-slate-900 dark:text-slate-300 dark:group-hover:text-orange-400">
              <Icon size={15} />
            </span>
            <span className="min-w-0 flex-1">
              <strong className="block text-[13px] font-semibold text-slate-800 group-hover:text-orange-700 dark:text-slate-200 dark:group-hover:text-orange-400">
                {title}
              </strong>
              <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{description}</span>
            </span>
            <ArrowRight
              size={14}
              aria-hidden="true"
              className="mt-1 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-orange-500 dark:text-slate-500"
            />
          </motion.button>
        ))}
      </div>

      <div className="mx-auto mt-5 flex max-w-xl flex-col items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
        <p>You can attach PDF, Word, text or Markdown files and ask about them.</p>
        <p className="flex items-center gap-1.5">
          <ShieldAlert size={13} aria-hidden="true" className="shrink-0 text-orange-600 dark:text-orange-400" />
          AI answers can contain mistakes. Test configuration changes in a non-production system first.
        </p>
      </div>
    </div>
  );
};
