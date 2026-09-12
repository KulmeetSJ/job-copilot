import React, { useState } from 'react';
import { 
  Briefcase, 
  Search, 
  Filter, 
  Sparkles, 
  Flame, 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRight, 
  Eye, 
  SlidersHorizontal,
  ExternalLink,
  Clock
} from 'lucide-react';
import { DashboardQueueItem, PriorityBand, QueueStatus } from '../types';
import { formatSource } from '../utils/formatters';

interface QueueViewProps {
  items: DashboardQueueItem[];
  loading: boolean;
  onRefresh: () => void;
  onInspectJob: (jobId: string) => void;
  onPrepareJob: (jobId: string) => void;
  onReviewApplication: (applicationId: string) => void;
  onSkipJob: (jobId: string) => void;
  selectedStatus?: QueueStatus;
  setSelectedStatus: (status?: QueueStatus) => void;
  selectedPriority?: PriorityBand;
  setSelectedPriority: (priority?: PriorityBand) => void;
  minScore: number;
  setMinScore: (score: number) => void;
}

export const QueueView: React.FC<QueueViewProps> = ({
  items,
  loading,
  onRefresh,
  onInspectJob,
  onPrepareJob,
  onReviewApplication,
  onSkipJob,
  selectedStatus,
  setSelectedStatus,
  selectedPriority,
  setSelectedPriority,
  minScore,
  setMinScore,
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredItems = items.filter((item) => {
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const matchText = `${item.company} ${item.title} ${item.location || ''} ${item.key_matched_skills.join(' ')} ${item.source || ''}`.toLowerCase();
      if (!matchText.includes(q)) return false;
    }
    return true;
  });

  const getPriorityBadge = (band: PriorityBand) => {
    switch (band) {
      case 'CRITICAL':
        return <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30 flex items-center space-x-1"><Flame className="w-3 h-3 text-rose-400" /><span>CRITICAL</span></span>;
      case 'HIGH':
        return <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-semibold bg-blue-500/15 text-blue-300 border border-blue-500/30 flex items-center space-x-1"><Sparkles className="w-3 h-3 text-blue-400" /><span>HIGH</span></span>;
      case 'MEDIUM':
        return <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">MEDIUM</span>;
      case 'LOW':
        return <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-semibold bg-slate-500/15 text-slate-400 border border-slate-500/30">LOW</span>;
      default:
        return null;
    }
  };

  const getRecommendationBadge = (rec?: string) => {
    if (!rec) return null;
    switch (rec.toUpperCase()) {
      case 'STRONG_APPLY':
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">STRONG APPLY</span>;
      case 'APPLY':
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">APPLY</span>;
      case 'REVIEW':
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">REVIEW</span>;
      case 'SKIP':
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">SKIP</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-slate-800 text-slate-300">{rec}</span>;
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      
      {/* Controls & Filter Bar */}
      <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search companies, roles, technologies (e.g. Java, GCP, Stripe)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-slate-900/80 border border-slate-700/80 rounded-lg text-xs sm:text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          {/* Quick Filters */}
          <div className="flex flex-wrap items-center gap-2">
            
            {/* Priority Filter */}
            <select
              value={selectedPriority || ''}
              onChange={(e) => setSelectedPriority(e.target.value ? (e.target.value as PriorityBand) : undefined)}
              className="flex-1 sm:flex-initial px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            {/* Status Filter */}
            <select
              value={selectedStatus || ''}
              onChange={(e) => setSelectedStatus(e.target.value ? (e.target.value as QueueStatus) : undefined)}
              className="flex-1 sm:flex-initial px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Statuses</option>
              <option value="NEW">New</option>
              <option value="REVIEW">Review</option>
              <option value="APPROVED">Approved</option>
              <option value="PREPARING">Preparing</option>
              <option value="READY_FOR_REVIEW">Ready for Review</option>
            </select>

            {/* Min Score Slider Tooltip */}
            <div className="flex items-center space-x-2 bg-slate-900 px-3 py-1.5 border border-slate-700 rounded-lg">
              <span className="text-[11px] text-slate-400 whitespace-nowrap">Min: {minScore}%</span>
              <input
                type="range"
                min="0"
                max="90"
                step="5"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-16 sm:w-20 accent-blue-500 cursor-pointer"
              />
            </div>

            <button
              onClick={onRefresh}
              className="px-3 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 active:bg-slate-900 text-slate-200 rounded-lg transition-colors border border-slate-700"
            >
              Refresh
            </button>

          </div>
        </div>
      </div>

      {/* Opportunities List */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="glass-panel p-8 sm:p-12 rounded-xl text-center space-y-3">
          <Briefcase className="w-10 h-10 text-slate-500 mx-auto" />
          <h4 className="text-sm font-semibold text-slate-300">No opportunities match criteria</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Adjust your search query, priority filters, or match score threshold to inspect more opportunities.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredItems.map((job) => (
            <div
              key={job.job_id}
              className="glass-card p-4 sm:p-5 rounded-xl border border-slate-800/80 hover:border-blue-500/40 space-y-3 sm:space-y-4"
            >
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                
                {/* Job Title & Company */}
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-sm sm:text-base text-white hover:text-blue-300 transition-colors">
                      {job.company}
                    </span>
                    <span className="text-slate-600 hidden sm:inline">•</span>
                    <span className="text-xs sm:text-sm font-medium text-slate-300">
                      {job.title}
                    </span>
                    {job.canonical_url && (
                      <a 
                        href={job.canonical_url} 
                        target="_blank" 
                        rel="noopener noreferrer" 
                        className="text-slate-400 hover:text-blue-400"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
                    <span>{job.location || 'Remote / Unspecified'}</span>
                    <span>•</span>
                    <span className="font-medium text-slate-300">{formatSource(job.source)}</span>
                    <span>•</span>
                    <span className="flex items-center space-x-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      <span>{job.freshness_days === 0 ? 'Today' : `${job.freshness_days}d ago`}</span>
                    </span>
                  </div>
                </div>

                {/* Score & Badges */}
                <div className="flex flex-wrap items-center gap-2">
                  {getPriorityBadge(job.priority_band)}
                  {getRecommendationBadge(job.recommendation)}
                  
                  {job.match_score !== undefined && job.match_score !== null && (
                    <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 font-mono">
                      <span className="text-[11px] text-slate-400">Match</span>
                      <span className="text-xs sm:text-sm font-bold text-white">{Math.round(job.match_score)}%</span>
                    </div>
                  )}
                </div>

              </div>

              {/* Matched Skills & Gaps Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-slate-800/60 text-xs">
                
                {/* Matched Skills */}
                <div className="space-y-1.5">
                  <span className="text-[10px] sm:text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Matched Evidence:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {job.key_matched_skills.length === 0 ? (
                      <span className="text-slate-500 italic">No specific skills tagged</span>
                    ) : (
                      job.key_matched_skills.map((skill, idx) => (
                        <span 
                          key={idx}
                          className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-medium text-[11px]"
                        >
                          ✓ {skill}
                        </span>
                      ))
                    )}
                  </div>
                </div>

                {/* Major Gaps / Risks */}
                <div className="space-y-1.5">
                  <span className="text-[10px] sm:text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Requirement Gaps / Flags:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {job.major_gaps.length === 0 && job.risk_flags.length === 0 ? (
                      <span className="text-slate-500 italic">No critical risks flagged</span>
                    ) : (
                      [...job.major_gaps, ...job.risk_flags].map((gap, idx) => (
                        <span 
                          key={idx}
                          className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-medium text-[11px]"
                        >
                          ! {gap}
                        </span>
                      ))
                    )}
                  </div>
                </div>

              </div>

              {/* Primary Reasoning Snippet */}
              {job.primary_reason && (
                <div className="p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80 text-xs text-slate-300 flex items-start space-x-2">
                  <span className="font-semibold text-blue-400 whitespace-nowrap">Reason:</span>
                  <span>{job.primary_reason}</span>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 pt-2 border-t border-slate-800/60">
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-slate-400">
                    Queue: <span className="font-mono text-slate-300 font-semibold">{job.queue_status}</span>
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:flex sm:items-center gap-2">
                  <button
                    onClick={() => onInspectJob(job.job_id)}
                    className="px-3 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors border border-slate-700 flex items-center justify-center space-x-1.5"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>Inspect</span>
                  </button>

                  <button
                    onClick={() => onPrepareJob(job.job_id)}
                    className="px-3 py-2 text-xs font-medium bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 rounded-lg transition-colors border border-blue-500/30 flex items-center justify-center space-x-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Prepare</span>
                  </button>

                  <button
                    onClick={() => onReviewApplication(job.tracking_application_id || job.job_id)}
                    className="col-span-2 sm:col-span-1 px-3.5 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors shadow-sm flex items-center justify-center space-x-1.5"
                  >
                    <span>Review Application</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>

                  <button
                    onClick={() => onSkipJob(job.job_id)}
                    className="col-span-2 sm:col-span-1 px-2.5 py-2 text-xs text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors text-center"
                  >
                    Skip
                  </button>
                </div>
              </div>

            </div>
          ))}
        </div>
      )}

    </div>
  );
};
