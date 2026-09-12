import React, { useState } from 'react';
import { 
  Flame, 
  Sparkles, 
  Eye, 
  Send, 
  HelpCircle, 
  Award, 
  Globe2, 
  Clock, 
  ArrowRight,
  ShieldCheck,
  CheckCircle,
  AlertCircle,
  Link2,
  FileText,
  Download,
  ExternalLink,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Info
} from 'lucide-react';
import { DashboardOverviewResponse, AnalyzeOpportunityResponse } from '../types';
import { api } from '../api';
import { formatSource } from '../utils/formatters';

interface OverviewViewProps {
  overview: DashboardOverviewResponse | null;
  onNavigateTab: (tab: string) => void;
  onSelectJob?: (jobId: string) => void;
}

const ANALYSIS_STEPS = [
  'Reading job posting',
  'Understanding requirements',
  'Matching your profile',
  'Tailoring resume',
  'Preparing application'
];

export const OverviewView: React.FC<OverviewViewProps> = ({
  overview,
  onNavigateTab,
  onSelectJob,
}) => {
  const [jobUrl, setJobUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<AnalyzeOpportunityResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadResume = async () => {
    if (!analysisResult?.resume_download_url) return;
    try {
      setIsDownloading(true);
      await api.downloadFile(analysisResult.resume_download_url, 'Tailored_Resume.pdf');
    } catch (err: any) {
      alert(err.message || 'Failed to download resume');
    } finally {
      setIsDownloading(false);
    }
  };

  const handleAnalyzeOpportunity = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanUrl = jobUrl.trim();
    if (!cleanUrl || isAnalyzing) return;

    setIsAnalyzing(true);
    setCurrentStepIndex(0);
    setAnalysisResult(null);
    setAnalysisError(null);

    // Realistic progressive step transitions matching backend stages
    const timer = setInterval(() => {
      setCurrentStepIndex((prev) => (prev < ANALYSIS_STEPS.length - 1 ? prev + 1 : prev));
    }, 1800);

    try {
      const result = await api.analyzeOpportunity(cleanUrl);
      clearInterval(timer);
      setCurrentStepIndex(ANALYSIS_STEPS.length - 1);
      setAnalysisResult(result);
    } catch (err: any) {
      clearInterval(timer);
      setAnalysisError(err.message || 'Failed to analyze opportunity.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleClearForm = () => {
    setJobUrl('');
    setAnalysisResult(null);
    setAnalysisError(null);
    setIsAnalyzing(false);
  };

  if (!overview) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const { queue_counts, pipeline_counts, recent_activity, active_sources_count, healthy_sources_count, authenticated_sessions_count } = overview;

  const pipelineStages = [
    { label: 'Discovered', count: pipeline_counts.discovered, color: 'text-slate-400', bg: 'bg-slate-800/40' },
    { label: 'Recommended', count: pipeline_counts.recommended, color: 'text-blue-400', bg: 'bg-blue-900/20' },
    { label: 'Prepared', count: pipeline_counts.prepared, color: 'text-indigo-400', bg: 'bg-indigo-900/20' },
    { label: 'Ready for Review', count: pipeline_counts.ready_for_review, color: 'text-amber-400', bg: 'bg-amber-900/20' },
    ...(pipeline_counts.submission_unverified > 0 ? [
      { label: 'Unverified', count: pipeline_counts.submission_unverified, color: 'text-amber-400', bg: 'bg-amber-950/20' }
    ] : []),
    { label: 'Submitted', count: pipeline_counts.submitted, color: 'text-emerald-400', bg: 'bg-emerald-900/20' },
    { label: 'Interview', count: pipeline_counts.interview, color: 'text-purple-400', bg: 'bg-purple-900/20' },
    { label: 'Offer', count: pipeline_counts.offer, color: 'text-yellow-300', bg: 'bg-yellow-900/20' },
  ];

  return (
    <div className="space-y-6">
      
      {/* Top Banner / Review Notice */}
      <div className="glass-panel p-4 rounded-xl border border-blue-500/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Human Review Control Active</h2>
            <p className="text-xs text-slate-400">
              Applications are never sent without your review and explicit authorization.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
            System Online
          </span>
        </div>
      </div>

      {/* User-Submitted Opportunity Card: "Found a job yourself?" */}
      <div className="glass-panel p-5 sm:p-6 rounded-2xl border border-blue-500/25 bg-gradient-to-b from-blue-950/20 to-slate-900/40 relative overflow-hidden shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <Link2 className="w-4 h-4" />
              </div>
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Found a job yourself?
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-300">
              Paste a job posting URL and I'll analyze the opportunity, match it against your profile, and prepare the application.
            </p>
          </div>
          <span className="text-[11px] text-slate-400 bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800 self-start md:self-auto whitespace-nowrap">
            Works with supported job boards and company career pages.
          </span>
        </div>

        {/* Input & Form */}
        <form onSubmit={handleAnalyzeOpportunity} className="mt-4 flex flex-col sm:flex-row items-stretch gap-2.5">
          <div className="relative flex-1">
            <input
              type="url"
              required
              placeholder="Paste job URL (e.g. https://jobs.lever.co/company/job-id or company career link)..."
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              disabled={isAnalyzing}
              className="w-full pl-4 pr-4 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all disabled:opacity-50"
            />
          </div>
          <button
            type="submit"
            disabled={isAnalyzing || !jobUrl.trim()}
            className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:from-slate-800 disabled:to-slate-800 disabled:text-slate-500 text-white font-semibold text-xs sm:text-sm rounded-xl transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center space-x-2 shrink-0"
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-blue-300" />
                <span>Analyzing Opportunity...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-blue-200" />
                <span>Analyze Opportunity</span>
              </>
            )}
          </button>
        </form>

        {/* Processing State: Live Step Indicators */}
        {isAnalyzing && (
          <div className="mt-5 p-4 rounded-xl bg-slate-950/60 border border-blue-500/20 space-y-3 animate-fadeIn">
            <div className="flex items-center justify-between text-xs text-slate-300 font-medium">
              <span className="flex items-center space-x-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
                <span>Processing opportunity...</span>
              </span>
              <span className="text-blue-400 font-mono">
                Stage {currentStepIndex + 1} of {ANALYSIS_STEPS.length}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 pt-1">
              {ANALYSIS_STEPS.map((step, idx) => {
                const isCompleted = idx < currentStepIndex;
                const isCurrent = idx === currentStepIndex;
                return (
                  <div
                    key={step}
                    className={`p-2 rounded-lg text-[11px] font-medium transition-all flex items-center space-x-1.5 ${
                      isCompleted
                        ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                        : isCurrent
                        ? 'bg-blue-500/15 text-blue-300 border border-blue-500/30 animate-pulse'
                        : 'bg-slate-900/40 text-slate-500 border border-slate-800/40'
                    }`}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    ) : isCurrent ? (
                      <Loader2 className="w-3 h-3 animate-spin text-blue-400 shrink-0" />
                    ) : (
                      <div className="w-3 h-3 rounded-full border border-slate-700 shrink-0 text-[9px] flex items-center justify-center font-mono">
                        {idx + 1}
                      </div>
                    )}
                    <span className="truncate">{step}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error State */}
        {analysisError && (
          <div className="mt-4 p-4 rounded-xl bg-rose-950/20 border border-rose-500/30 text-rose-300 flex items-start space-x-3 text-xs sm:text-sm">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div className="flex-1 space-y-1">
              <p className="font-semibold text-rose-200">Unable to Process Opportunity</p>
              <p className="text-rose-300/90 text-xs">{analysisError}</p>
            </div>
            <button
              onClick={() => setAnalysisError(null)}
              className="text-xs text-rose-400 hover:text-rose-200"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Duplicate State */}
        {analysisResult && analysisResult.is_duplicate && (
          <div className="mt-4 p-4 sm:p-5 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-2 text-amber-300">
                <Info className="w-4 h-4 text-amber-400 shrink-0" />
                <h4 className="font-semibold text-sm">This opportunity is already in Job Copilot.</h4>
              </div>
              <button
                onClick={handleClearForm}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                Clear
              </button>
            </div>
            <div className="text-xs text-slate-300">
              <span className="font-medium text-white">{analysisResult.company}</span> • {analysisResult.title}
              {analysisResult.location && <span className="text-slate-400"> ({analysisResult.location})</span>}
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                onClick={() => {
                  if (onSelectJob) onSelectJob(analysisResult.job_id);
                }}
                className="px-3.5 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 text-xs font-semibold rounded-lg transition-colors flex items-center space-x-1.5"
              >
                <span>View Existing Opportunity</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => onNavigateTab('applications')}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors"
              >
                Go to Application Review
              </button>
            </div>
          </div>
        )}

        {/* Completion Result State */}
        {analysisResult && !analysisResult.is_duplicate && (
          <div className="mt-5 p-4 sm:p-5 rounded-xl bg-slate-950/80 border border-emerald-500/30 space-y-4 shadow-lg animate-fadeIn">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800/80">
              <div className="flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
                  Opportunity Analyzed & Prepared
                </span>
              </div>
              <button
                onClick={handleClearForm}
                className="text-xs text-slate-400 hover:text-slate-200 self-start sm:self-auto"
              >
                Analyze Another
              </button>
            </div>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold text-base text-white">{analysisResult.company}</span>
                  <span className="text-slate-600">•</span>
                  <span className="text-sm font-medium text-slate-300">{analysisResult.title}</span>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                  <span>{analysisResult.location || 'Remote / Flexible'}</span>
                  <span>•</span>
                  <span className="font-medium text-slate-300">{formatSource(analysisResult.source)}</span>
                  {analysisResult.selected_strategy && (
                    <>
                      <span>•</span>
                      <span className="font-mono text-emerald-300 text-[11px] uppercase">
                        Strategy: {analysisResult.selected_strategy.replace(/_/g, ' ')}
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Match Score & Recommendation Badge */}
              <div className="flex items-center space-x-2">
                <div className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 flex items-center space-x-2">
                  <span className="text-xs text-slate-400 font-medium">Match Fit</span>
                  <span className={`text-base font-bold font-mono ${
                    analysisResult.match_score >= 80 ? 'text-emerald-400' : analysisResult.match_score >= 60 ? 'text-blue-400' : 'text-amber-400'
                  }`}>
                    {Math.round(analysisResult.match_score)}%
                  </span>
                </div>
                <span className={`px-2.5 py-1.5 rounded-xl text-xs font-bold border ${
                  analysisResult.recommendation.toUpperCase().includes('APPLY')
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                }`}>
                  {analysisResult.recommendation.toUpperCase().replace(/_/g, ' ')}
                </span>
              </div>
            </div>

            {/* Strengths & Gaps Highlights */}
            {(analysisResult.strengths.length > 0 || analysisResult.gaps.length > 0) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-slate-800/60 text-xs">
                {analysisResult.strengths.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Key Strengths:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {analysisResult.strengths.slice(0, 4).map((str, idx) => (
                        <span key={idx} className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[11px]">
                          ✓ {str}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {analysisResult.gaps.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Gaps / Review Points:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {analysisResult.gaps.slice(0, 3).map((gap, idx) => (
                        <span key={idx} className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[11px]">
                          ! {gap}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/60">
              {onSelectJob && (
                <button
                  onClick={() => onSelectJob(analysisResult.job_id)}
                  className="px-3.5 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-colors flex items-center space-x-1.5"
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>View Opportunity</span>
                </button>
              )}

              {analysisResult.resume_download_url && (
                <button
                  onClick={handleDownloadResume}
                  disabled={isDownloading}
                  className="px-3.5 py-2 text-xs font-semibold bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded-lg transition-colors flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer"
                >
                  {isDownloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                  <span>{isDownloading ? 'Downloading...' : 'Download Resume'}</span>
                </button>
              )}

              <button
                onClick={() => onNavigateTab('applications')}
                className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors shadow-sm flex items-center space-x-1.5"
              >
                <span>Review Application</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>

              {analysisResult.supports_browser_prep && analysisResult.has_active_session && (
                <button
                  onClick={() => onNavigateTab('applications')}
                  className="px-3.5 py-2 text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded-lg transition-colors flex items-center space-x-1.5"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Prepare on Website</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>


      {/* KPI Stat Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        
        {/* Critical Priority */}
        <div 
          onClick={() => onNavigateTab('queue')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-rose-500/40"
        >
          <div className="flex items-center justify-between text-rose-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">Critical</span>
            <Flame className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white">{queue_counts.critical}</div>
          <p className="text-[11px] text-slate-400 mt-1">High-urgency matches</p>
        </div>

        {/* High Priority */}
        <div 
          onClick={() => onNavigateTab('queue')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-blue-500/40"
        >
          <div className="flex items-center justify-between text-blue-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">High Priority</span>
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white">{queue_counts.high}</div>
          <p className="text-[11px] text-slate-400 mt-1">Strong profile alignment</p>
        </div>

        {/* Ready For Review */}
        <div 
          onClick={() => onNavigateTab('applications')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-amber-500/40 bg-amber-950/10"
        >
          <div className="flex items-center justify-between text-amber-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">Review Ready</span>
            <Eye className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-amber-300">{pipeline_counts.ready_for_review}</div>
          <p className="text-[11px] text-amber-400/80 mt-1">Awaiting human review</p>
        </div>

        {/* Needs Input */}
        <div 
          onClick={() => onNavigateTab('applications')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-purple-500/40"
        >
          <div className="flex items-center justify-between text-purple-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">Needs Input</span>
            <HelpCircle className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-purple-300">{pipeline_counts.needs_user_input}</div>
          <p className="text-[11px] text-slate-400 mt-1">Sensitive questions</p>
        </div>

        {/* Submitted */}
        <div 
          onClick={() => onNavigateTab('tracking')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-emerald-500/40"
        >
          <div className="flex items-center justify-between text-emerald-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">Submitted</span>
            <Send className="w-4 h-4" />
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-white">{pipeline_counts.submitted}</span>
            {pipeline_counts.submission_unverified > 0 && (
              <span className="text-[10px] font-medium text-amber-400 font-mono bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                +{pipeline_counts.submission_unverified} unverified
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Confirmed applications</p>
        </div>

        {/* Interviews & Offers */}
        <div 
          onClick={() => onNavigateTab('tracking')}
          className="glass-card p-4 rounded-xl cursor-pointer hover:border-yellow-500/40"
        >
          <div className="flex items-center justify-between text-yellow-400 mb-2">
            <span className="text-xs font-semibold tracking-wide uppercase">Outcomes</span>
            <Award className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-yellow-300">
            {pipeline_counts.interview + pipeline_counts.offer}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">{pipeline_counts.interview} Interviews, {pipeline_counts.offer} Offers</p>
        </div>

      </div>

      {/* Application Lifecycle Pipeline Visual */}
      <div className="glass-panel p-5 rounded-xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <span>Application Pipeline Lifecycle</span>
          </h3>
          <button 
            onClick={() => onNavigateTab('tracking')}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
          >
            <span>View Kanban Board</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
          {pipelineStages.map((stage, idx) => (
            <div 
              key={stage.label}
              className={`p-3 rounded-lg border border-slate-800 ${stage.bg} flex flex-col justify-between`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400">{stage.label}</span>
                <span className="text-xs font-mono text-slate-500">#{idx + 1}</span>
              </div>
              <div className={`text-xl font-bold mt-2 ${stage.color}`}>{stage.count}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Row: Source Health & Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Source Health & Session Quick View */}
        <div className="glass-panel p-5 rounded-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
              <Globe2 className="w-4 h-4 text-blue-400" />
              <span>Source & Session Health</span>
            </h3>
            <button 
              onClick={() => onNavigateTab('sources')}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              Manage
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-slate-800">
              <div className="flex items-center space-x-2.5">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span className="text-xs text-slate-300 font-medium">Configured Sources</span>
              </div>
              <span className="text-xs font-mono font-semibold text-white">
                {healthy_sources_count} / {active_sources_count} Healthy
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-slate-800">
              <div className="flex items-center space-x-2.5">
                <ShieldCheck className="w-4 h-4 text-indigo-400" />
                <span className="text-xs text-slate-300 font-medium">Authenticated Sessions</span>
              </div>
              <span className="text-xs font-mono font-semibold text-indigo-300">
                {authenticated_sessions_count} Active
              </span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
            <span className="font-semibold text-slate-300">Zero Credential Exposure:</span> All session storage states are isolated on disk with strict permissions. Zero cookies or passwords are exposed to the UI.
          </div>
        </div>

        {/* Recent System Activity / Audit Feed */}
        <div className="glass-panel p-5 rounded-xl lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
              <Clock className="w-4 h-4 text-blue-400" />
              <span>Recent Operational Activity</span>
            </h3>
            <button 
              onClick={() => onNavigateTab('activity')}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              Full Log
            </button>
          </div>

          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
            {recent_activity.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">No recent events recorded.</div>
            ) : (
              recent_activity.map((act) => (
                <div 
                  key={act.event_id}
                  className="flex items-start justify-between p-2.5 rounded-lg bg-slate-900/40 border border-slate-800/80 text-xs"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-2">
                      <span className="px-1.5 py-0.5 rounded font-mono text-[10px] font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/20">
                        {act.event_type}
                      </span>
                      <span className="text-slate-300 font-medium">
                        {act.job_id || act.application_id}
                      </span>
                    </div>
                    {act.notes && (
                      <p className="text-slate-400 text-[11px]">{act.notes}</p>
                    )}
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 whitespace-nowrap ml-4">
                    {act.timestamp ? new Date(act.timestamp).toLocaleTimeString() : ''}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

    </div>
  );
};
