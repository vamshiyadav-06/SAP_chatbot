import React from 'react';
import { Database, Globe, Layers, AlertCircle } from 'lucide-react';

interface SourceTypeBadgeProps {
  sourceType?: 'knowledge_base' | 'web' | 'combined' | 'refusal' | 'error' | 'interrupted' | 'security_policy';
}

export const SourceTypeBadge: React.FC<SourceTypeBadgeProps> = ({ sourceType }) => {
  if (!sourceType) return null;

  if (sourceType === 'interrupted') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <AlertCircle className="w-3 h-3 text-amber-400" />
        <span>Generation Paused</span>
      </span>
    );
  }

  if (sourceType === 'knowledge_base') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-orange-500/15 text-orange-300 border border-orange-500/30">
        <Database className="w-3 h-3 text-orange-400" />
        <span>SAP Knowledge Base</span>
      </span>
    );
  }

  if (sourceType === 'web') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
        <Globe className="w-3 h-3 text-cyan-400" />
        <span>SAP Documentation (help.sap.com)</span>
      </span>
    );
  }

  if (sourceType === 'combined') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-500/15 text-purple-300 border border-purple-500/30">
        <Layers className="w-3 h-3 text-purple-400" />
        <span>Multi-Source Grounded</span>
      </span>
    );
  }

  if (sourceType === 'refusal') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <AlertCircle className="w-3 h-3 text-rose-400" />
        <span>SAP Scope Guardrail</span>
      </span>
    );
  }

  return null;
};
