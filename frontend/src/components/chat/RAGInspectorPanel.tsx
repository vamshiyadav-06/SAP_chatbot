import React, { useState, useEffect, useCallback } from 'react';
import {
  Database, FileText, Search, ChevronRight, ChevronDown, Globe, BookOpen,
  CheckCircle2, AlertCircle, XCircle, Loader2, BarChart2, Trophy, Zap,
  RefreshCw, Target, Shield
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

interface DocStatus {
  document_id: string | null;
  title: string;
  filename: string;
  file_size_mb: number;
  file_path: string;
  page_count: number;
  chunk_count: number;
  embedded_count: number;
  embedding_coverage: number;
  is_indexed: boolean;
  status: 'indexed' | 'not_indexed' | 'empty' | 'orphaned';
  file_hash: string | null;
}

interface Summary {
  total_files_discovered: number;
  total_files_indexed: number;
  total_files_not_indexed: number;
  total_chunks: number;
  total_embedded_chunks: number;
  overall_embedding_coverage: number;
  embedding_model: string;
  embedding_dim: number;
  internal_evidence_threshold: number;
  grounding_threshold: number;
  web_fallback_enabled: boolean;
}

interface ChunkRow {
  rank: number;
  chunk_id: string;
  document_name: string;
  page_number: number;
  section: string;
  vector_score: number;
  keyword_score: number;
  hybrid_score: number;
  rerank_score: number;
  snippet: string;
}

interface WebRow {
  rank: number;
  title: string;
  url: string;
  domain: string;
  score: number;
  authority_tier: number;
  snippet: string;
}

interface SearchResult {
  query: string;
  retrieval_summary: {
    total_candidates_retrieved: number;
    chunks_after_reranking: number;
    top_kb_rerank_score: number;
    has_sufficient_kb_evidence: boolean;
  };
  internal_confidence: {
    confidence: number;
    confidence_pct: string;
    threshold: number;
    passes_threshold: boolean;
    would_trigger_web_search: boolean;
    signals: Record<string, number>;
    reason: string;
  };
  web_search: {
    triggered: boolean;
    results_count: number;
    top_web_score: number;
    results: WebRow[];
  };
  evidence_selection: {
    selected_source: string;
    selected_evidence_quality: number;
    kb_wins: boolean;
    web_wins: boolean;
    summary: string;
    internal_eval: Record<string, unknown>;
    external_eval: Record<string, unknown>;
    combined_eval: Record<string, unknown>;
  };
  score_comparison: {
    kb_score: number;
    kb_score_pct: string;
    web_score: number;
    web_score_pct: string;
    winning_source: string;
    winning_score: number;
    winning_score_pct: string;
    score_difference: number;
  };
  top_chunks: ChunkRow[];
}

function ScoreBar({ score, color = 'orange', label }: { score: number; color?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  const colorMap: Record<string, string> = {
    orange: 'bg-orange-500',
    emerald: 'bg-emerald-500',
    cyan: 'bg-cyan-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
    violet: 'bg-violet-500',
  };
  const barColor = colorMap[color] || 'bg-orange-500';
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[10px] text-slate-400 w-28 shrink-0 truncate">{label}</span>}
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-mono text-slate-300 w-9 text-right shrink-0">{pct}%</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'indexed') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
      <CheckCircle2 className="w-3 h-3" /> Indexed
    </span>
  );
  if (status === 'not_indexed') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-950/60 text-amber-300 border border-amber-800/40">
      <AlertCircle className="w-3 h-3" /> Not Indexed
    </span>
  );
  if (status === 'orphaned') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-950/60 text-red-300 border border-red-800/40">
      <XCircle className="w-3 h-3" /> Orphaned
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">Empty</span>
  );
}

export const RAGInspectorPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'documents' | 'search'>('documents');
  const [docStatus, setDocStatus] = useState<{ summary: Summary; documents: DocStatus[] } | null>(null);
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [query, setQuery] = useState('');
  const [includeWeb, setIncludeWeb] = useState(false);
  const [topK, setTopK] = useState(8);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestResult, setIngestResult] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoadingDocs(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/rag-inspect/documents`, {
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDocStatus(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  const runSimilaritySearch = async () => {
    if (!query.trim()) return;
    setLoadingSearch(true);
    setError(null);
    setSearchResult(null);
    try {
      const res = await fetch(`${API_BASE}/rag-inspect/similarity-search`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), top_k: topK, include_web_search: includeWeb })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSearchResult(await res.json());
      setActiveTab('search');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoadingSearch(false);
    }
  };

  const runIngestion = async () => {
    setIngestLoading(true);
    setIngestResult(null);
    try {
      const res = await fetch(`${API_BASE}/admin/documents/ingest`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json', 'X-Admin-Key': 'sap-admin-dev-secret-key-999' }
      });
      const data = await res.json();
      const details: Array<{status: string}> = data.details || [];
      const ingested = details.filter(d => d.status === 'ingested').length;
      const skipped = details.filter(d => d.status === 'skipped').length;
      setIngestResult(`Done: ${ingested} ingested, ${skipped} skipped. Total: ${details.length} files.`);
      await fetchDocuments();
    } catch (e: unknown) {
      setIngestResult(`Error: ${e instanceof Error ? e.message : 'Failed'}`);
    } finally {
      setIngestLoading(false);
    }
  };

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  const toggleChunk = (rank: number) => {
    setExpandedChunks(prev => {
      const next = new Set(prev);
      if (next.has(rank)) next.delete(rank); else next.add(rank);
      return next;
    });
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.75) return 'emerald';
    if (score >= 0.55) return 'orange';
    if (score >= 0.35) return 'amber';
    return 'red';
  };

  return (
    <div className="w-full bg-[#07070d] border border-[#1a1a28] rounded-2xl overflow-hidden shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 bg-gradient-to-r from-[#0a0a14] to-[#0d0d1a] border-b border-[#1a1a28]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-orange-500/20 border border-orange-500/30 flex items-center justify-center">
            <Database className="w-4 h-4 text-orange-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">RAG Pipeline Inspector</h2>
            <p className="text-[10px] text-slate-400">Indexing · Similarity · Score comparison · Evidence winner</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchDocuments} className="p-1.5 rounded-lg text-slate-400 hover:text-orange-400 hover:bg-orange-500/10 transition cursor-pointer" title="Refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={runIngestion} disabled={ingestLoading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/15 hover:bg-orange-500/25 text-orange-300 border border-orange-500/30 text-xs font-medium transition cursor-pointer disabled:opacity-50">
            {ingestLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
            Run Ingestion
          </button>
        </div>
      </div>

      {ingestResult && (
        <div className="px-5 py-2 bg-emerald-950/40 border-b border-emerald-800/30 text-[11px] text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> {ingestResult}
        </div>
      )}
      {error && (
        <div className="px-5 py-2 bg-red-950/40 border-b border-red-800/30 text-[11px] text-red-300 flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
        </div>
      )}

      {/* Search Bar */}
      <div className="px-5 py-3 border-b border-[#1a1a28] bg-[#09090f]">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runSimilaritySearch()}
              placeholder="Test a query to check retrieval quality & scores..."
              className="w-full pl-9 pr-3 py-2 bg-[#111118] border border-[#1e1e2c] rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20"
            />
          </div>
          <select value={topK} onChange={e => setTopK(Number(e.target.value))} className="px-2 py-1.5 bg-[#111118] border border-[#1e1e2c] rounded-xl text-xs text-slate-300 cursor-pointer">
            {[5, 8, 10, 15].map(k => <option key={k} value={k}>Top {k}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none whitespace-nowrap">
            <input type="checkbox" checked={includeWeb} onChange={e => setIncludeWeb(e.target.checked)} className="accent-orange-500 cursor-pointer" />
            +Web
          </label>
          <button onClick={runSimilaritySearch} disabled={loadingSearch || !query.trim()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-orange-500 hover:bg-orange-400 text-black text-xs font-bold transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
            {loadingSearch ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
            Search
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#1a1a28]">
        {(['documents', 'search'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} className={`flex-1 py-2.5 text-xs font-semibold transition cursor-pointer ${activeTab === tab ? 'text-orange-400 border-b-2 border-orange-500 bg-orange-500/5' : 'text-slate-400 hover:text-slate-200'}`}>
            {tab === 'documents' ? (
              <span className="flex items-center justify-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> Knowledge Base
                {docStatus && <span className="ml-1 px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-300 text-[10px]">{docStatus.summary.total_files_indexed}/{docStatus.summary.total_files_discovered}</span>}
              </span>
            ) : (
              <span className="flex items-center justify-center gap-1.5">
                <BarChart2 className="w-3.5 h-3.5" /> Score Analysis
                {searchResult && <span className="ml-1 w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Documents Tab */}
      {activeTab === 'documents' && (
        <div className="overflow-y-auto max-h-[70vh]">
          {loadingDocs ? (
            <div className="flex items-center justify-center py-12 gap-2 text-slate-400 text-xs">
              <Loader2 className="w-4 h-4 animate-spin text-orange-400" /> Loading...
            </div>
          ) : docStatus ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-[#08080e]">
                {[
                  { label: 'Discovered', value: docStatus.summary.total_files_discovered, color: 'text-slate-300' },
                  { label: 'Indexed', value: docStatus.summary.total_files_indexed, color: 'text-emerald-400' },
                  { label: 'Not Indexed', value: docStatus.summary.total_files_not_indexed, color: 'text-amber-400' },
                  { label: 'Total Chunks', value: docStatus.summary.total_chunks.toLocaleString(), color: 'text-orange-400' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-[#0c0c14] border border-[#1a1a26] rounded-xl p-3">
                    <div className={`text-lg font-bold ${color}`}>{value}</div>
                    <div className="text-[10px] text-slate-500">{label}</div>
                  </div>
                ))}
              </div>
              <div className="px-4 pb-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-slate-400">Embedding Coverage</span>
                  <span className="text-[10px] font-mono text-orange-400">{Math.round(docStatus.summary.overall_embedding_coverage * 100)}% ({docStatus.summary.total_embedded_chunks.toLocaleString()}/{docStatus.summary.total_chunks.toLocaleString()} chunks)</span>
                </div>
                <ScoreBar score={docStatus.summary.overall_embedding_coverage} color="orange" />
                <div className="mt-1.5 text-[10px] text-slate-500">
                  Model: <span className="text-slate-400">{docStatus.summary.embedding_model}</span> · Dim: <span className="text-slate-400">{docStatus.summary.embedding_dim}</span> · KB Threshold: <span className="text-orange-400">{Math.round(docStatus.summary.internal_evidence_threshold * 100)}%</span> · Grounding: <span className="text-orange-400">{Math.round(docStatus.summary.grounding_threshold * 100)}%</span>
                </div>
              </div>
              <div className="divide-y divide-[#111118]">
                {docStatus.documents.map((doc, idx) => (
                  <div key={idx} className={`px-4 py-3 flex items-start gap-3 hover:bg-[#0c0c14] transition ${!doc.is_indexed ? 'opacity-70' : ''}`}>
                    <div className="mt-0.5 shrink-0">
                      {doc.is_indexed ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2 flex-wrap">
                        <span className="text-xs font-medium text-slate-200 truncate max-w-xs" title={doc.filename}>{doc.filename}</span>
                        <div className="flex items-center gap-2 shrink-0">
                          <StatusBadge status={doc.status} />
                          <span className="text-[10px] text-slate-500">{doc.file_size_mb} MB</span>
                        </div>
                      </div>
                      {doc.is_indexed && (
                        <>
                          <div className="mt-1.5 grid grid-cols-3 gap-3">
                            <div><div className="text-[10px] text-slate-500 mb-0.5">Chunks</div><div className="text-xs font-semibold text-slate-200">{doc.chunk_count.toLocaleString()}</div></div>
                            <div><div className="text-[10px] text-slate-500 mb-0.5">Embedded</div><div className="text-xs font-semibold text-emerald-400">{doc.embedded_count.toLocaleString()}</div></div>
                            <div><div className="text-[10px] text-slate-500 mb-0.5">Coverage</div><div className="text-xs font-semibold text-orange-400">{Math.round(doc.embedding_coverage * 100)}%</div></div>
                          </div>
                          <div className="mt-1.5"><ScoreBar score={doc.embedding_coverage} color={doc.embedding_coverage >= 0.9 ? 'emerald' : 'amber'} /></div>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}

      {/* Search Analysis Tab */}
      {activeTab === 'search' && (
        <div className="overflow-y-auto max-h-[70vh]">
          {loadingSearch ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin text-orange-400" />
              Running full retrieval pipeline...
            </div>
          ) : searchResult ? (
            <div className="divide-y divide-[#111118]">
              {/* Query Info */}
              <div className="px-5 py-3 bg-[#08080e]">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Query tested</div>
                <div className="text-sm text-slate-100 font-medium">"{searchResult.query}"</div>
                <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-slate-400">
                  <span>Retrieved: <strong className="text-slate-200">{searchResult.retrieval_summary.total_candidates_retrieved}</strong></span>
                  <span>Reranked to: <strong className="text-slate-200">{searchResult.retrieval_summary.chunks_after_reranking}</strong></span>
                  <span>Top KB score: <strong className="text-orange-400">{Math.round(searchResult.retrieval_summary.top_kb_rerank_score * 100)}%</strong></span>
                  <span className={searchResult.retrieval_summary.has_sufficient_kb_evidence ? 'text-emerald-400' : 'text-amber-400'}>
                    {searchResult.retrieval_summary.has_sufficient_kb_evidence ? '✓ Sufficient KB' : '⚠ Insufficient KB'}
                  </span>
                </div>
              </div>

              {/* Score Comparison - KEY DISPLAY */}
              <div className="px-5 py-4 bg-[#09090f]">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Trophy className="w-3.5 h-3.5 text-orange-400" /> Score Comparison: KB vs Web
                </div>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  {/* KB */}
                  <div className={`p-3 rounded-xl border ${searchResult.evidence_selection.kb_wins ? 'bg-emerald-950/30 border-emerald-700/40' : 'bg-[#0d0d1a] border-[#1a1a28]'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <BookOpen className="w-3.5 h-3.5 text-orange-400" />
                        <span className="text-xs font-semibold text-slate-200">Knowledge Base</span>
                      </div>
                      {searchResult.evidence_selection.kb_wins && (
                        <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded-full">
                          <Trophy className="w-3 h-3" /> Winner
                        </span>
                      )}
                    </div>
                    <div className={`text-2xl font-bold mb-1 ${searchResult.score_comparison.kb_score >= 0.70 ? 'text-emerald-400' : searchResult.score_comparison.kb_score >= 0.50 ? 'text-orange-400' : 'text-amber-400'}`}>
                      {searchResult.score_comparison.kb_score_pct}
                    </div>
                    <div className="text-[10px] text-slate-400 mb-2">Internal Evidence Confidence</div>
                    <ScoreBar score={searchResult.score_comparison.kb_score} color={searchResult.score_comparison.kb_score >= 0.70 ? 'emerald' : 'orange'} />
                    <div className={`mt-1.5 text-[10px] font-medium ${searchResult.internal_confidence.passes_threshold ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {searchResult.internal_confidence.passes_threshold ? '✓ Above 70% threshold' : '⚠ Below 70% → triggers web search'}
                    </div>
                  </div>
                  {/* Web */}
                  <div className={`p-3 rounded-xl border ${searchResult.evidence_selection.web_wins ? 'bg-cyan-950/30 border-cyan-700/40' : 'bg-[#0d0d1a] border-[#1a1a28]'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-xs font-semibold text-slate-200">Web Search</span>
                      </div>
                      {searchResult.evidence_selection.web_wins && (
                        <span className="flex items-center gap-1 text-[10px] font-bold text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded-full">
                          <Trophy className="w-3 h-3" /> Winner
                        </span>
                      )}
                    </div>
                    <div className={`text-2xl font-bold mb-1 ${searchResult.web_search.triggered ? (searchResult.score_comparison.web_score >= 0.50 ? 'text-cyan-400' : 'text-amber-400') : 'text-slate-600'}`}>
                      {searchResult.web_search.triggered ? searchResult.score_comparison.web_score_pct : 'N/A'}
                    </div>
                    <div className="text-[10px] text-slate-400 mb-2">
                      {searchResult.web_search.triggered ? `${searchResult.web_search.results_count} results (SAP domains)` : 'Not triggered (KB ≥ 70%)'}
                    </div>
                    {searchResult.web_search.triggered ? (
                      <ScoreBar score={searchResult.score_comparison.web_score} color="cyan" />
                    ) : (
                      <div className="text-[10px] text-slate-600">Web search only runs when KB confidence is 60-70%</div>
                    )}
                  </div>
                </div>
                {/* Winner */}
                <div className="p-3 rounded-xl bg-[#0c0c16] border border-[#1e1e2c]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Shield className="w-3.5 h-3.5 text-orange-400" />
                      <span className="text-xs font-semibold text-slate-200">Selected Evidence Source</span>
                    </div>
                    <span className={`text-xs font-bold px-3 py-1 rounded-lg border ${
                      searchResult.evidence_selection.selected_source === 'knowledge_base' ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40' :
                      searchResult.evidence_selection.selected_source === 'web' ? 'bg-cyan-950/60 text-cyan-300 border-cyan-800/40' :
                      searchResult.evidence_selection.selected_source === 'combined' ? 'bg-violet-950/60 text-violet-300 border-violet-800/40' :
                      'bg-amber-950/60 text-amber-300 border-amber-800/40'
                    }`}>
                      {searchResult.evidence_selection.selected_source.replace('_', ' ').toUpperCase()} · {searchResult.score_comparison.winning_score_pct}
                    </span>
                  </div>
                  <p className="mt-2 text-[10px] text-slate-400 leading-relaxed">{searchResult.evidence_selection.summary}</p>
                </div>
              </div>

              {/* Confidence Signals */}
              <div className="px-5 py-4">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Target className="w-3.5 h-3.5 text-orange-400" /> KB Evidence Confidence Signals (5 factors)
                </div>
                <div className="space-y-2">
                  {Object.entries(searchResult.internal_confidence.signals).map(([signal, value]) => {
                    const labels: Record<string, string> = {
                      top_relevance: 'Top Relevance (35%)',
                      term_coverage: 'Term Coverage (25%)',
                      technical_id_match: 'Tech ID Match (20%)',
                      domain_alignment: 'Domain Align (10%)',
                      consistency: 'Consistency (10%)',
                    };
                    return <ScoreBar key={signal} score={value as number} color={getScoreColor(value as number)} label={labels[signal] || signal} />;
                  })}
                </div>
                {searchResult.internal_confidence.reason && (
                  <div className="mt-2.5 text-[10px] text-slate-500 bg-[#0c0c14] border border-[#181820] rounded-lg px-3 py-2 leading-relaxed">
                    {searchResult.internal_confidence.reason}
                  </div>
                )}
                {searchResult.internal_confidence.would_trigger_web_search && (
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-amber-300 bg-amber-950/30 border border-amber-800/30 rounded-lg px-3 py-2">
                    <Globe className="w-3.5 h-3.5 shrink-0" />
                    KB confidence ({searchResult.internal_confidence.confidence_pct}) below 70% → Web search was triggered
                  </div>
                )}
              </div>

              {/* Top Chunks */}
              <div className="px-5 py-4">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <BarChart2 className="w-3.5 h-3.5 text-orange-400" />
                  Top Retrieved Chunks · Scores
                  <span className="ml-1 text-slate-600">({searchResult.top_chunks.length} shown)</span>
                </div>
                <div className="space-y-2">
                  {searchResult.top_chunks.map((chunk) => (
                    <div key={chunk.rank} className={`rounded-xl border transition ${chunk.rerank_score >= 0.70 ? 'border-orange-500/30 bg-orange-950/10' : 'border-[#1a1a28] bg-[#0c0c14]'}`}>
                      <button onClick={() => toggleChunk(chunk.rank)} className="w-full px-3 py-2.5 flex items-center gap-3 cursor-pointer">
                        <span className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 ${chunk.rerank_score >= 0.70 ? 'bg-orange-500/25 text-orange-300' : 'bg-slate-800 text-slate-400'}`}>
                          {chunk.rank}
                        </span>
                        <div className="flex-1 min-w-0 text-left">
                          <div className="text-xs font-medium text-slate-200 truncate">{chunk.document_name}</div>
                          <div className="text-[10px] text-slate-500">p.{chunk.page_number} · {chunk.section}</div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0 text-[10px]">
                          <span className="text-slate-500">Vec:</span>
                          <span className={`font-mono font-semibold ${chunk.vector_score >= 0.65 ? 'text-emerald-400' : 'text-slate-300'}`}>{Math.round(chunk.vector_score * 100)}%</span>
                          <span className="text-slate-700">|</span>
                          <span className="text-slate-500">KW:</span>
                          <span className="font-mono text-slate-300">{Math.round(chunk.keyword_score * 100)}%</span>
                          <span className="text-slate-700">|</span>
                          <span className="text-slate-500">Final:</span>
                          <span className={`font-mono font-bold ${chunk.rerank_score >= 0.70 ? 'text-orange-400' : 'text-slate-200'}`}>{Math.round(chunk.rerank_score * 100)}%</span>
                          {expandedChunks.has(chunk.rank) ? <ChevronDown className="w-3.5 h-3.5 text-slate-500 ml-1" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500 ml-1" />}
                        </div>
                      </button>
                      <div className="px-3 pb-2 space-y-1">
                        <ScoreBar score={chunk.vector_score} color="violet" label="Vector Sim" />
                        <ScoreBar score={chunk.keyword_score} color="cyan" label="BM25 Keyword" />
                        <ScoreBar score={chunk.hybrid_score} color="orange" label="Hybrid (60v+40k)" />
                        <ScoreBar score={chunk.rerank_score} color={getScoreColor(chunk.rerank_score)} label="Final Rerank" />
                      </div>
                      {expandedChunks.has(chunk.rank) && (
                        <div className="px-3 pb-3">
                          <div className="p-2.5 bg-[#080810] border border-[#161622] rounded-lg text-[11px] text-slate-400 leading-relaxed font-mono whitespace-pre-wrap">
                            {chunk.snippet}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Web Results */}
              {searchResult.web_search.triggered && searchResult.web_search.results.length > 0 && (
                <div className="px-5 py-4">
                  <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-cyan-400" /> Web Results (help.sap.com approved)
                  </div>
                  <div className="space-y-2">
                    {searchResult.web_search.results.map((w) => (
                      <div key={w.rank} className="p-3 rounded-xl bg-[#0c0c14] border border-[#1a1a28]">
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div>
                            <a href={w.url} target="_blank" rel="noopener noreferrer" className="text-xs font-semibold text-cyan-400 hover:underline">{w.title}</a>
                            <div className="text-[10px] text-slate-500 mt-0.5">{w.domain} · Tier {w.authority_tier}</div>
                          </div>
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-lg shrink-0 ${w.score >= 0.60 ? 'bg-cyan-950/60 text-cyan-300' : 'bg-slate-800 text-slate-400'}`}>
                            {Math.round(w.score * 100)}%
                          </span>
                        </div>
                        <ScoreBar score={w.score} color="cyan" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-500 text-xs">
              <Search className="w-8 h-8 opacity-30" />
              <span>Enter a query above and click Search to analyze retrieval scores</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
