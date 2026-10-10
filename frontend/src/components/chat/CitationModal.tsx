import React from 'react';
import { X, FileText, Award, Hash, BookOpen, Globe } from 'lucide-react';
import type { Citation, WebSource } from '../../types';

interface CitationModalProps {
  citations?: Citation[];
  webSources?: WebSource[];
  isOpen: boolean;
  onClose: () => void;
}

export const CitationModal: React.FC<CitationModalProps> = ({
  citations = [],
  webSources = [],
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  const hasCitations = citations.length > 0;
  const hasWebSources = webSources.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/75 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/90 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/70 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-orange-500/10 dark:bg-orange-500/20 text-orange-600 dark:text-orange-400 border border-orange-500/25 dark:border-orange-500/30">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Sources &amp; Citations</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {hasCitations
                  ? `${citations.length} verified private SAP documentation ${citations.length === 1 ? 'source' : 'sources'}`
                  : `${webSources.length} verified authoritative web ${webSources.length === 1 ? 'reference' : 'references'}`}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content Body */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1">
          {/* Knowledge Base Citations */}
          {hasCitations && (
            <div className="space-y-4">
              {citations.map((c, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 hover:border-orange-500/40 transition space-y-3"
                >
                  {/* Citation Meta Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-850 pb-2.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-5 h-5 rounded-md bg-orange-500/15 dark:bg-orange-500/20 border border-orange-500/30 text-orange-600 dark:text-orange-300 text-xs font-bold flex items-center justify-center shrink-0">
                        {idx + 1}
                      </span>
                      <div className="flex items-center gap-1.5 min-w-0">
                        <BookOpen className="w-3.5 h-3.5 text-orange-500 dark:text-orange-400 shrink-0" />
                        <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate" title={c.document}>
                          {c.document}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-950/40 px-2 py-0.5 rounded-md border border-emerald-300 dark:border-emerald-800/40">
                        <Hash className="w-3 h-3" />
                        Page {c.page}
                      </span>
                      {c.score > 0 && (
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${c.score >= 0.70 ? 'bg-orange-500' : c.score >= 0.50 ? 'bg-amber-500' : 'bg-slate-500'}`}
                              style={{ width: `${Math.round(c.score * 100)}%` }}
                            />
                          </div>
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-orange-700 dark:text-orange-300 bg-orange-100 dark:bg-orange-950/50 px-2 py-0.5 rounded-md border border-orange-300 dark:border-orange-500/30">
                            <Award className="w-3 h-3 text-orange-500 dark:text-orange-400" />
                            {Math.round(c.score * 100)}% match
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {c.section && (
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
                      Section: <span className="text-slate-700 dark:text-slate-300">{c.section}</span>
                    </div>
                  )}

                  {/* Excerpt */}
                  <div>
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1">
                      Verified Excerpt
                    </span>
                    <div className="p-3 bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800/80 rounded-lg text-xs leading-relaxed text-slate-700 dark:text-slate-300 font-mono">
                      "{c.snippet}"
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Web Sources Fallback */}
          {hasWebSources && (
            <div className="space-y-4">
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
                Authoritative Web Sources (help.sap.com Whitelist)
              </div>
              {webSources.map((w, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 hover:border-cyan-500/40 transition space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <Globe className="w-4 h-4 text-cyan-600 dark:text-cyan-400 shrink-0" />
                      <a
                        href={w.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-semibold text-cyan-600 dark:text-cyan-400 hover:underline truncate"
                      >
                        {w.title}
                      </a>
                    </div>
                    <span className="text-[10px] text-slate-600 dark:text-slate-400 bg-slate-200 dark:bg-slate-800 px-2 py-0.5 rounded">
                      {w.domain}
                    </span>
                  </div>
                  <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-mono bg-white dark:bg-slate-900/80 p-2.5 rounded border border-slate-200 dark:border-slate-800">
                    "{w.snippet}"
                  </p>
                </div>
              ))}
            </div>
          )}

          {!hasCitations && !hasWebSources && (
            <div className="text-center py-8 text-slate-400 text-xs">
              <BookOpen className="w-8 h-8 text-slate-400 dark:text-slate-500 mx-auto mb-2 opacity-60" />
              No citation data available for this message.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
