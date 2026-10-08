import React from 'react';
import { Database, Globe, AlertTriangle } from 'lucide-react';

interface SourceTypeBadgeProps {
  sourceType?: 'knowledge_base' | 'web' | 'refusal' | 'error' | 'interrupted';
}

export const SourceTypeBadge: React.FC<SourceTypeBadgeProps> = ({ sourceType }) => {
  if (!sourceType) return null;

  if (sourceType === 'interrupted') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <span>Generation Stopped</span>
      </span>
    );
  }

  if (sourceType === 'knowledge_base') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-sap-600/15 text-sap-300 border border-sap-500/30">
        <Database className="w-3.5 h-3.5 text-sap-400" />
        <span>Private SAP Knowledge Base</span>
      </span>
    );
  }

  if (sourceType === 'web') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
        <Globe className="w-3.5 h-3.5 text-cyan-400" />
        <span>Official SAP Web Fallback</span>
      </span>
    );
  }

  if (sourceType === 'refusal') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
        <span>SAP Scope Restriction</span>
      </span>
    );
  }

  return null;
};
