import React from 'react';
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
  AlertCircle
} from 'lucide-react';
import { DashboardOverviewResponse } from '../types';

interface OverviewViewProps {
  overview: DashboardOverviewResponse | null;
  onNavigateTab: (tab: string) => void;
  onSelectJob?: (jobId: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  overview,
  onNavigateTab,
}) => {
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
    { label: 'Submitted', count: pipeline_counts.submitted, color: 'text-emerald-400', bg: 'bg-emerald-900/20' },
    { label: 'Interview', count: pipeline_counts.interview, color: 'text-purple-400', bg: 'bg-purple-900/20' },
    { label: 'Offer', count: pipeline_counts.offer, color: 'text-yellow-300', bg: 'bg-yellow-900/20' },
  ];

  return (
    <div className="space-y-6">
      
      {/* Top Banner / Invariant Notice */}
      <div className="glass-panel p-4 rounded-xl border border-blue-500/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Human Control Invariant Active</h2>
            <p className="text-xs text-slate-400">
              Applications are never submitted autonomously. Review, preparation, and explicit confirmation remain strictly human-driven.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
            Authoritative Engine Online
          </span>
        </div>
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
          <div className="text-2xl font-bold text-white">{pipeline_counts.submitted}</div>
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
