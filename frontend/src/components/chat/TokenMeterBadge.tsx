import React from 'react';
import { Zap } from 'lucide-react';
import type { TokenUsage } from '../../types';
import { TOKEN_ESTIMATE_NOTE, formatTokenCost } from './tokenSavings';
import { TOKEN_ALLOWANCE, refillText, type TokenWallet } from './TokenBalance';

interface TokenMeterBadgeProps {
  /** True while the answer streams. */
  streaming?: boolean;
  /** Final figures once the answer is complete. */
  usage?: TokenUsage;
  /** Tokens left of the allowance after this answer (latest answer only). */
  wallet?: TokenWallet | null;
}

const badgeClass =
  'inline-flex items-center gap-1.5 shrink-0 px-2.5 py-0.5 rounded-full text-[11px] font-medium border shadow-sm select-none bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/50';

/** Answer header badge opposite "Clyptus.AI": the free tokens this answer used (0 to 1). The comparison
 *  with other chatbots stays in the pop-up after each answer. */
export const TokenMeterBadge: React.FC<TokenMeterBadgeProps> = ({ streaming = false, usage, wallet }) => {
  if (typeof usage?.cost === 'number') {
    const used = `You used only ${formatTokenCost(usage.cost)}`;
    const refill = wallet ? refillText(wallet.refillAt) : null;
    const left = wallet
      ? ` · ${wallet.balance.toLocaleString('en-US', { maximumFractionDigits: 3 })} of ${TOKEN_ALLOWANCE.toLocaleString('en-US')} left${refill ? `, refills ${refill}` : ''}`
      : '';
    const text = `${used}${left}`;
    return (
      <span title={TOKEN_ESTIMATE_NOTE} aria-label={text} className={badgeClass}>
        <span aria-hidden="true">😊</span>
        <span aria-hidden="true" className="tabular-nums font-semibold">{text}</span>
      </span>
    );
  }
  if (streaming) {
    return (
      <span title={TOKEN_ESTIMATE_NOTE} className={badgeClass}>
        <span aria-hidden="true">😊</span>
        <Zap className="w-3 h-3 text-orange-500 animate-pulse" aria-hidden="true" />
        <span>Counting tokens…</span>
      </span>
    );
  }
  return null;
};
