import React from 'react';
import { X, ExternalLink, BookOpen, Layers, CheckCircle, Zap, Shield, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface AssistantGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AssistantGuideModal: React.FC<AssistantGuideModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="w-full max-w-xl bg-[#09090f] border border-[#1e1e2c] rounded-2xl p-6 shadow-2xl text-slate-200 relative animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-[#181824]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-orange-600 to-amber-500 flex items-center justify-center text-white shadow-lg shadow-orange-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span>SAP + BRIM Assistant</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-400 border border-orange-500/30 font-semibold">
                  v2.0 Enterprise
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Specialized AI knowledge engine for SAP Billing and Revenue Innovation Management
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Core Modules Grid */}
        <div className="mt-4">
          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-orange-400" />
            <span>Supported Architecture Modules</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-3 rounded-xl bg-[#0e0e18] border border-[#1a1a2a]">
              <strong className="text-orange-400 block mb-1">SOM</strong>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Subscription Order Management: Provider orders, provider contracts, and master agreements.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[#0e0e18] border border-[#1a1a2a]">
              <strong className="text-orange-400 block mb-1">CC</strong>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Convergent Charging: Real-time rating, allowances, charging logic, and charge plans.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[#0e0e18] border border-[#1a1a2a]">
              <strong className="text-orange-400 block mb-1">CI</strong>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Convergent Invoicing: Billable Items (BITs), Consumption Items (CITs), and invoicing.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[#0e0e18] border border-[#1a1a2a]">
              <strong className="text-orange-400 block mb-1">FI-CA</strong>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Contract Accounts A/R & A/P: High-volume billing, clearing, payments, and open item mgmt.
              </p>
            </div>
          </div>
        </div>

        {/* Quick Capabilities */}
        <div className="mt-4 p-3 rounded-xl bg-[#0d0d16] border border-[#181826] text-xs">
          <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>How to Get the Best Answers</span>
          </div>
          <ul className="space-y-1.5 text-slate-300 text-[11px]">
            <li className="flex items-center gap-2">
              <CheckCircle className="w-3 h-3 text-emerald-400 shrink-0" />
              <span>Ask detailed technical questions (e.g., T-codes, SPRO paths, table structures).</span>
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle className="w-3 h-3 text-emerald-400 shrink-0" />
              <span>Ask contextual follow-up questions to drill into specific steps or components.</span>
            </li>
            <li className="flex items-center gap-2">
              <Shield className="w-3 h-3 text-cyan-400 shrink-0" />
              <span>Every response is claim-verified against indexed official documentation.</span>
            </li>
          </ul>
        </div>

        {/* Actions / Links */}
        <div className="mt-5 pt-4 border-t border-[#181824] flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs">
            <button
              onClick={() => {
                onClose();
                navigate('/how-it-works');
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-slate-300 hover:text-white bg-[#141420] hover:bg-[#1c1c2e] border border-[#232336] transition cursor-pointer"
            >
              <BookOpen className="w-3.5 h-3.5 text-orange-400" />
              <span>How It Works</span>
            </button>
            <a
              href="https://help.sap.com/docs/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-slate-300 hover:text-white bg-[#141420] hover:bg-[#1c1c2e] border border-[#232336] transition cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5 text-cyan-400" />
              <span>SAP Help Portal</span>
            </a>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-semibold text-xs transition cursor-pointer shadow-md shadow-orange-600/20"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};
