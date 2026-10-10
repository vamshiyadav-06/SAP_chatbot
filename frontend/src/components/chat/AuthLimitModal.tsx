import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ArrowRight, Lock, CheckCircle2, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import companyIcon from '../../assets/clyptusap-icon.png';

interface AuthLimitModalProps {
  isOpen: boolean;
  onClose: () => void;
  questionCount: number;
}

export const AuthLimitModal: React.FC<AuthLimitModalProps> = ({
  isOpen,
  onClose,
  questionCount,
}) => {
  const navigate = useNavigate();

  if (!isOpen) return null;

  const handleGoToAuth = (mode: 'login' | 'register') => {
    onClose();
    navigate(`/login?mode=${mode}`);
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/80 backdrop-blur-md transition-opacity"
        />

        {/* Modal Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94, y: 16 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="relative w-full max-w-lg rounded-2xl bg-[#09090d] border border-[#22222d] shadow-2xl shadow-orange-500/10 p-6 sm:p-8 text-slate-100 z-10 overflow-hidden"
        >
          {/* Subtle Orange Glow behind header */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-32 bg-orange-500/15 blur-3xl pointer-events-none rounded-full" />

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60 transition"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>

          {/* Brand Icon Header */}
          <div className="flex items-center gap-3.5 mb-5">
            <div className="w-12 h-12 rounded-xl bg-orange-500/10 border border-orange-500/30 flex items-center justify-center shadow-lg shadow-orange-500/10 p-2">
              <img src={companyIcon} alt="Clyptus Icon" className="w-full h-full object-contain" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-orange-400 tracking-wider uppercase">
                <Lock size={12} />
                <span>Free Preview Limit</span>
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Continue with Clyptusap.ai
              </h2>
            </div>
          </div>

          {/* Description */}
          <p className="text-sm text-slate-300 leading-relaxed mb-6">
            You've reached your free preview limit ({questionCount} of 2 questions). Create a free account or sign in to continue asking unlimited SAP & BRIM questions with grounded citations.
          </p>

          {/* Feature list */}
          <div className="space-y-2.5 mb-7 bg-[#0f0f16] border border-[#1b1b26] rounded-xl p-4">
            <div className="flex items-start gap-2.5 text-xs text-slate-200">
              <CheckCircle2 size={15} className="text-orange-400 shrink-0 mt-0.5" />
              <span><strong>Unlimited Questions:</strong> Ask about any S/4HANA, FI-CA, CC, or CI scenario.</span>
            </div>
            <div className="flex items-start gap-2.5 text-xs text-slate-200">
              <CheckCircle2 size={15} className="text-orange-400 shrink-0 mt-0.5" />
              <span><strong>Authoritative Citations:</strong> Exact document pages, sections, and similarity scores.</span>
            </div>
            <div className="flex items-start gap-2.5 text-xs text-slate-200">
              <CheckCircle2 size={15} className="text-orange-400 shrink-0 mt-0.5" />
              <span><strong>Saved History & Workspaces:</strong> Organize threads into pinned enterprise projects.</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="space-y-2.5">
            <button
              type="button"
              onClick={() => handleGoToAuth('register')}
              className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-orange-600 to-orange-500 hover:from-orange-500 hover:to-orange-400 text-white font-semibold text-sm shadow-lg shadow-orange-500/25 flex items-center justify-center gap-2 transition cursor-pointer"
            >
              <Sparkles size={16} />
              Create Free Account
              <ArrowRight size={15} />
            </button>
            <button
              type="button"
              onClick={() => handleGoToAuth('login')}
              className="w-full py-2.5 px-4 rounded-xl bg-[#14141d] hover:bg-[#1a1a27] border border-[#272738] text-slate-200 hover:text-white font-medium text-sm transition cursor-pointer"
            >
              Already have an account? Sign In
            </button>
          </div>

          <p className="text-[11px] text-center text-slate-500 mt-4">
            Enterprise-grade tenant isolation · No training on confidential data
          </p>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
