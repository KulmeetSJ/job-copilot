import React, { useState, useEffect } from 'react';
import { 
  X, 
  ExternalLink, 
  Sparkles, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  HelpCircle, 
  BookOpen, 
  FileText,
  Clock,
  Layers
} from 'lucide-react';
import { api } from '../api';
import { JobDetailResponse, MatchClassification } from '../types';

interface JobDetailModalProps {
  jobId: string;
  onClose: () => void;
  onPrepare: (jobId: string) => void;
  onReview: (jobId: string) => void;
}

export const JobDetailModal: React.FC<JobDetailModalProps> = ({
  jobId,
  onClose,
  onPrepare,
  onReview,
}) => {
  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFullDesc, setShowFullDesc] = useState(false);

  useEffect(() => {
    let isMounted = true;
    api.getJobDetail(jobId)
      .then((data) => {
        if (isMounted) {
          setDetail(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load job details');
          setLoading(false);
        }
      });
    return () => { isMounted = false; };
  }, [jobId]);

  const getClassificationBadge = (cls: MatchClassification) => {
    switch (cls) {
      case 'MATCH_CONFIRMED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">CONFIRMED WORK</span>;
      case 'MATCH_PROJECT_ONLY':
        return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30">PROJECT EVIDENCE</span>;
      case 'MATCH_EXPOSURE_ONLY':
        return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">HANDS-ON EXPOSURE</span>;
      case 'PARTIAL_MATCH':
        return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30">PARTIAL MATCH</span>;
      case 'NO_EVIDENCE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-700/50 text-slate-400 border border-slate-600/30">NO EVIDENCE</span>;
      case 'CONFLICT':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">CONFLICT</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">{cls}</span>;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-[#0c121e] border border-slate-700 rounded-2xl max-w-4xl w-full my-8 max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex items-start justify-between bg-slate-900/40">
          <div className="space-y-1">
            <div className="flex items-center space-x-3">
              <h2 className="text-xl font-bold text-white tracking-tight">
                {detail?.company || 'Loading...'}
              </h2>
              <span className="text-slate-600">•</span>
              <span className="text-base text-slate-300 font-medium">
                {detail?.title}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
              <span>{detail?.location || 'Remote'}</span>
              <span>•</span>
              <span className="capitalize">{detail?.source}</span>
              <span>•</span>
              <span>ID: <code className="font-mono text-slate-300">{jobId}</code></span>
              {detail?.url && (
                <a 
                  href={detail.url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="text-blue-400 hover:underline flex items-center space-x-1"
                >
                  <span>Portal Link</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-sm">
          {loading ? (
            <div className="flex items-center justify-center min-h-[300px]">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
          ) : error || !detail ? (
            <div className="p-6 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300">
              {error || 'Failed to load details.'}
            </div>
          ) : (
            <>
              {/* Top Score Summary Banner */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
                  <span className="text-xs text-slate-400 font-medium">Overall Fit Score</span>
                  <div className="text-2xl font-bold text-white mt-1">{detail.match_score}%</div>
                </div>
                <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
                  <span className="text-xs text-slate-400 font-medium">Recommendation</span>
                  <div className="text-lg font-bold text-blue-400 mt-1">{detail.recommendation}</div>
                </div>
                <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
                  <span className="text-xs text-slate-400 font-medium">Priority Band</span>
                  <div className="text-lg font-bold text-indigo-300 mt-1">{detail.priority_band} ({detail.priority_score})</div>
                </div>
                <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
                  <span className="text-xs text-slate-400 font-medium">Resume Strategy</span>
                  <div className="text-sm font-bold text-emerald-400 mt-1 font-mono uppercase">{detail.recommended_strategy}</div>
                </div>
              </div>

              {/* 7-Dimensional Match Breakdown */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <Layers className="w-4 h-4 text-blue-400" />
                  <span>Phase 4 Evaluation Breakdown (7 Dimensions)</span>
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {detail.dimension_scores.map((dim) => (
                    <div 
                      key={dim.dimension_name}
                      className="p-3 rounded-lg bg-slate-900/50 border border-slate-800/80 space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-300">{dim.dimension_name}</span>
                        <span className="font-mono font-bold text-white">{Math.round(dim.score)}% <span className="text-slate-500 font-normal">({Math.round(dim.weight * 100)}% wt)</span></span>
                      </div>
                      
                      {/* Score Bar */}
                      <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${
                            dim.score >= 80 ? 'bg-emerald-500' : dim.score >= 60 ? 'bg-blue-500' : 'bg-amber-500'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(0, dim.score))}%` }}
                        />
                      </div>
                      <p className="text-[11px] text-slate-400">{dim.description}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* FACT vs INFERENCE vs RECOMMENDATION */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-indigo-400" />
                  <span>Structured Explanation (Fact vs Inference vs Recommendation)</span>
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  
                  {/* Facts */}
                  <div className="p-4 rounded-xl bg-emerald-950/15 border border-emerald-500/20 space-y-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center space-x-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Verified Facts</span>
                    </span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {detail.explanation.facts.map((f, i) => (
                        <li key={i} className="flex items-start space-x-1.5">
                          <span className="text-emerald-400">•</span>
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Inferences */}
                  <div className="p-4 rounded-xl bg-blue-950/15 border border-blue-500/20 space-y-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-blue-400 flex items-center space-x-1.5">
                      <HelpCircle className="w-3.5 h-3.5" />
                      <span>Derived Inferences</span>
                    </span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {detail.explanation.inferences.map((inf, i) => (
                        <li key={i} className="flex items-start space-x-1.5">
                          <span className="text-blue-400">•</span>
                          <span>{inf}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Recommendations */}
                  <div className="p-4 rounded-xl bg-purple-950/15 border border-purple-500/20 space-y-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center space-x-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Action Advice</span>
                    </span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {detail.explanation.recommendations.map((r, i) => (
                        <li key={i} className="flex items-start space-x-1.5">
                          <span className="text-purple-400">•</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                </div>
              </div>

              {/* Requirement Match Evidence Table */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-400" />
                  <span>Requirement Match Provenance</span>
                </h3>

                <div className="border border-slate-800 rounded-xl overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold">
                      <tr>
                        <th className="p-3">Requirement</th>
                        <th className="p-3">Classification</th>
                        <th className="p-3">Confidence</th>
                        <th className="p-3">Evidence Provenance / Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
                      {detail.requirement_matches.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="p-4 text-center text-slate-500">No structured requirement matches recorded.</td>
                        </tr>
                      ) : (
                        detail.requirement_matches.map((rm, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/30">
                            <td className="p-3 font-medium text-slate-200">
                              <div>{rm.requirement_name}</div>
                              <span className="text-[10px] text-slate-500">{rm.category} {rm.is_must_have ? '• Must-Have' : '• Preferred'}</span>
                            </td>
                            <td className="p-3">
                              {getClassificationBadge(rm.classification)}
                            </td>
                            <td className="p-3 font-mono text-slate-300">
                              {Math.round(rm.confidence * 100)}%
                            </td>
                            <td className="p-3 text-slate-400">
                              <div>{rm.reason}</div>
                              {rm.evidence_ids.length > 0 && (
                                <div className="text-[10px] font-mono text-blue-400 mt-0.5">
                                  Cited: {rm.evidence_ids.join(', ')}
                                </div>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Full Job Description Accordion */}
              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300">Full Job Posting Text</span>
                  <button 
                    onClick={() => setShowFullDesc(!showFullDesc)}
                    className="text-xs text-blue-400 hover:text-blue-300 font-medium"
                  >
                    {showFullDesc ? 'Collapse' : 'Expand Description'}
                  </button>
                </div>
                {showFullDesc && (
                  <pre className="text-xs text-slate-400 whitespace-pre-wrap font-sans bg-slate-950 p-4 rounded-lg border border-slate-800 max-h-60 overflow-y-auto leading-relaxed">
                    {detail.description}
                  </pre>
                )}
              </div>

            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/40 flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200"
          >
            Close
          </button>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => { onPrepare(jobId); onClose(); }}
              className="px-4 py-2 text-xs font-semibold bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded-lg transition-colors flex items-center space-x-1.5"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Prepare Application</span>
            </button>

            <button
              onClick={() => { onReview(jobId); onClose(); }}
              className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
            >
              Open Application Review
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
