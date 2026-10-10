import React, { useState } from 'react';
import { CheckCircle2, Sparkles, AlertCircle, Info, Target } from 'lucide-react';

interface GroundingScoreBadgeProps {
  score?: number;
  verificationStatus?: 'verified' | 'partial' | 'unverified' | 'abstention' | 'restricted';
}

export const GroundingScoreBadge: React.FC<GroundingScoreBadgeProps> = ({
  score,
  verificationStatus
}) => {
  const [showTooltip, setShowTooltip] = useState(false);

  if (score === undefined || score === null) return null;

  const pct = Math.max(1, Math.min(99, Math.round(score * 100)));

  // Honest score display aligned with recalibrated grounding scoring
  let colorStyles = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40 shadow-sm shadow-emerald-950/30';
  let label = 'Grounding';
  let Icon = CheckCircle2;
  let description = `Evidence grounding: ${pct}%. Measures how well the answer is supported by retrieved documentation.`;

  if (pct >= 80) {
    colorStyles = 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50 shadow-sm shadow-emerald-500/20';
    label = 'Grounding';
    Icon = CheckCircle2;
    description = `Strong grounding (${pct}%). Answer well-supported by internal SAP documentation with high claim verification.`;
  } else if (pct >= 65) {
    colorStyles = 'bg-orange-500/15 text-orange-400 border-orange-500/35 shadow-sm shadow-orange-950/30';
    label = 'Grounding';
    Icon = Target;
    description = `Good grounding (${pct}%). Most claims verified against indexed documentation. Some supplementation.`;
  } else if (pct >= 50) {
    colorStyles = 'bg-amber-500/15 text-amber-400 border-amber-500/35';
    label = 'Grounding';
    Icon = Sparkles;
    description = `Moderate grounding (${pct}%). Partial evidence match. Web search may have been triggered (60-70% range).`;
  } else {
    colorStyles = 'bg-red-900/30 text-red-300 border-red-700/50';
    label = 'Low Evidence';
    Icon = AlertCircle;
    description = `Low grounding (${pct}%). Insufficient evidence in indexed documents. Answer relies on general domain knowledge.`;
  }

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setShowTooltip(!showTooltip)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${colorStyles} transition hover:scale-105 active:scale-95 cursor-pointer backdrop-blur-md`}
      >
        <Icon className="w-3.5 h-3.5 shrink-0" />
        <span>{label}: {pct}%</span>
        <Info className="w-3 h-3 opacity-60 ml-0.5" />
      </button>

      {showTooltip && (
        <div className="absolute bottom-full left-0 mb-2 w-72 p-3 bg-[#0a0a10] border border-slate-800 rounded-xl shadow-2xl z-30 text-xs text-slate-300 pointer-events-none animate-in fade-in zoom-in-95">
          <div className="font-semibold text-slate-100 mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-orange-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Evidence Verification
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 bg-emerald-950/80 text-emerald-300 border border-emerald-800/40 rounded-full capitalize">
              {verificationStatus || 'Verified'} • {pct}%
            </span>
          </div>
          <p className="text-[11px] leading-relaxed text-slate-400 mt-1">
            {description}
          </p>
        </div>
      )}
    </div>
  );
};
