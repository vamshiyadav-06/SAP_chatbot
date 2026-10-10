import React from 'react';
import { ArrowRight, CircleHelp, Search, Settings2, Workflow } from 'lucide-react';
import { motion } from 'framer-motion';
import iconOnly from '../../assets/clyptusap-icon.png';

interface WelcomeScreenProps {
  onSelectPrompt: (prompt: string) => void;
}

const suggestions = [
  {
    icon: Workflow,
    title: 'Explain a BRIM process',
    description: 'Explore convergent invoicing & charging step by step',
    prompt: 'Can you explain the end-to-end SAP BRIM billing and invoicing process flow?',
  },
  {
    icon: Search,
    title: 'Find a transaction code',
    description: 'Look up a relevant SAP transaction code',
    prompt: 'What SAP transaction code is used for monitoring billable items in Convergent Invoicing?',
  },
  {
    icon: Settings2,
    title: 'Help with FI-CA',
    description: 'Ask about Contract Accounts Receivable and Payable',
    prompt: 'How are document types and posting areas configured in SAP FI-CA?',
  },
  {
    icon: CircleHelp,
    title: 'Troubleshoot an SAP issue',
    description: 'Start with an error code or billing symptom',
    prompt: 'My billing process completed in BRIM but no invoice document was generated. What should I check?',
  },
];

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onSelectPrompt }) => {
  return (
    <div className="chat-empty w-full max-w-2xl mx-auto text-center px-4 py-8">
      {/* Brand Icon with Electric Orange Glow */}
      <motion.div
        className="chat-empty-icon mx-auto mb-4 w-12 h-12 rounded-2xl bg-gradient-to-tr from-orange-600 via-orange-500 to-orange-400 p-2 shadow-lg shadow-orange-500/30 flex items-center justify-center border border-orange-400/50"
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        <img src={iconOnly} alt="Clyptusap.ai" className="w-full h-full object-contain filter drop-shadow-sm" />
      </motion.div>

      <span className="eyebrow tracking-wider text-xs font-semibold text-orange-600 dark:text-orange-400">
        SAP + BRIM KNOWLEDGE ASSISTANT
      </span>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 dark:text-white mt-2 mb-2">
        Ask about <span className="text-orange-500 dark:text-orange-400">SAP.</span>
      </h1>

      <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto mb-6">
        Explore SAP and BRIM through grounded enterprise knowledge conversations.
      </p>

      {/* Suggestion Cards Grid */}
      <div className="suggestion-grid grid grid-cols-1 sm:grid-cols-2 gap-3 text-left max-w-xl mx-auto">
        {suggestions.map(({ icon: Icon, title, description, prompt }, index) => (
          <motion.button
            key={title}
            onClick={() => onSelectPrompt(prompt)}
            className="suggestion-card p-3 rounded-xl bg-white dark:bg-[#09090e] hover:bg-orange-50/50 dark:hover:bg-[#12121c] border border-slate-200 dark:border-[#1a1a26] hover:border-orange-300 dark:hover:border-orange-500/50 transition flex items-start gap-3 text-left group cursor-pointer shadow-sm hover:shadow-md dark:hover:shadow-orange-500/10"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.08 }}
          >
            <span className="p-2 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-500 dark:text-orange-400 group-hover:text-orange-600 dark:group-hover:text-orange-300 group-hover:bg-orange-500/20 transition shrink-0">
              <Icon size={16} />
            </span>
            <div className="flex-1 min-w-0">
              <strong className="block text-xs font-semibold text-slate-800 dark:text-slate-200 group-hover:text-orange-600 dark:group-hover:text-white truncate">
                {title}
              </strong>
              <small className="block text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1">
                {description}
              </small>
            </div>
            <ArrowRight size={14} className="text-slate-400 dark:text-slate-500 group-hover:text-orange-500 dark:group-hover:text-orange-400 group-hover:translate-x-0.5 transition-transform shrink-0 mt-1" />
          </motion.button>
        ))}
      </div>

      <div className="chat-start-note flex items-center justify-center gap-2 mt-8 text-xs text-slate-400 dark:text-slate-500">
        <span className="tiny-status w-2 h-2 rounded-full bg-orange-500 inline-block animate-pulse" />
        <span>RAG Pipeline Active</span>
        <span>·</span>
        <span>Grounded in verified enterprise documentation</span>
      </div>

    </div>
  );
};
