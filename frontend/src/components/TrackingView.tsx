import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  Search, 
  ExternalLink, 
  Clock, 
  ChevronRight, 
  CheckCircle, 
  AlertCircle,
  Filter,
  ArrowRight
} from 'lucide-react';
import { api } from '../api';
import { formatSource } from '../utils/formatters';

interface TrackingViewProps {
  onSelectApplication: (applicationId: string) => void;
}

export const TrackingView: React.FC<TrackingViewProps> = ({ onSelectApplication }) => {
  const [applications, setApplications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterQuery, setFilterQuery] = useState('');
  const [activeMobileStage, setActiveMobileStage] = useState<string>('ALL');

  useEffect(() => {
    api.listApplications().then((data) => {
      setApplications(data);
      setLoading(false);
    });
  }, []);

  const columns = [
    { id: 'DISCOVERED', label: 'Discovered', fullLabel: 'Discovered & Recommended', statuses: ['DISCOVERED', 'RECOMMENDED', 'SHORTLISTED'] },
    { id: 'PREPARED', label: 'Prepared', fullLabel: 'Prepared & Review', statuses: ['PREPARED', 'READY_FOR_REVIEW', 'READY_TO_APPLY', 'WAITING_FOR_USER', 'PREPARING'] },
    { id: 'UNVERIFIED', label: 'Unverified', fullLabel: 'Unverified / Needs Review', statuses: ['SUBMISSION_UNVERIFIED', 'EXTERNAL_SUBMISSION_UNVERIFIED', 'MANUAL_ACTION_REQUIRED'] },
    { id: 'SUBMITTED', label: 'Submitted', fullLabel: 'Submitted & Sent', statuses: ['SUBMITTED', 'APPLIED', 'ACKNOWLEDGED'] },
    { id: 'IN_PROGRESS', label: 'Assessment', fullLabel: 'Response & Assessment', statuses: ['RECRUITER_RESPONSE', 'ASSESSMENT', 'OA'] },
    { id: 'INTERVIEW', label: 'Interview', fullLabel: 'Interviewing', statuses: ['INTERVIEW', 'FINAL_ROUND'] },
    { id: 'OFFER', label: 'Offer', fullLabel: 'Offer & Decision', statuses: ['OFFER', 'ACCEPTED'] },
    { id: 'ARCHIVED', label: 'Closed', fullLabel: 'Closed / Rejected', statuses: ['REJECTED', 'WITHDRAWN', 'EXPIRED', 'CLOSED'] },
  ];

  const getAppStatus = (app: any): string => {
    return (app.current_status || app.status || 'DISCOVERED').toString().toUpperCase();
  };

  const filtered = applications.filter((app) => {
    if (!filterQuery) return true;
    const q = filterQuery.toLowerCase();
    const st = getAppStatus(app);
    return `${app.company || ''} ${app.role || ''} ${st} ${app.source || ''}`.toLowerCase().includes(q);
  });

  const getStageCounts = () => {
    const counts: Record<string, number> = { ALL: filtered.length };
    columns.forEach(col => {
      counts[col.id] = filtered.filter((a) => col.statuses.includes(getAppStatus(a))).length;
    });
    return counts;
  };

  const stageCounts = getStageCounts();

  const displayedColumns = activeMobileStage === 'ALL' 
    ? columns 
    : columns.filter(c => c.id === activeMobileStage);

  return (
    <div className="space-y-4 sm:space-y-6">
      
      {/* Header */}
      <div className="glass-panel p-4 sm:p-5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <Activity className="w-5 h-5 text-blue-400" />
            <span>Application Tracking</span>
          </h2>
          <p className="text-[11px] sm:text-xs text-slate-400 mt-0.5">
            Track and manage your applications across all lifecycle stages from discovery to offer.
          </p>
        </div>

        <div className="w-full md:w-64">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Filter by company, role..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Mobile Stage Selector Tabs (Phone / Tablet) */}
      <div className="lg:hidden flex items-center space-x-1.5 overflow-x-auto py-1 scrollbar-none no-scrollbar -mx-2 px-2">
        <button
          onClick={() => setActiveMobileStage('ALL')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap shrink-0 transition-colors flex items-center space-x-1.5 ${
            activeMobileStage === 'ALL'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200'
          }`}
        >
          <span>All Stages</span>
          <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
            activeMobileStage === 'ALL' ? 'bg-white/20 text-white' : 'bg-slate-800 text-slate-400'
          }`}>
            {stageCounts.ALL}
          </span>
        </button>

        {columns.map((col) => {
          const isSelected = activeMobileStage === col.id;
          const count = stageCounts[col.id] || 0;
          return (
            <button
              key={col.id}
              onClick={() => setActiveMobileStage(col.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap shrink-0 transition-colors flex items-center space-x-1.5 ${
                isSelected
                  ? 'bg-blue-600 text-white font-semibold shadow-sm'
                  : 'bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200'
              }`}
            >
              <span>{col.label}</span>
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                isSelected ? 'bg-white/20 text-white font-bold' : 'bg-slate-800 text-slate-400'
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Kanban Board / Responsive Lanes */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3 sm:gap-3.5">
          {displayedColumns.map((col) => {
            const colApps = filtered.filter((a) => col.statuses.includes(getAppStatus(a)));
            return (
              <div 
                key={col.id}
                className="bg-slate-900/50 border border-slate-800 rounded-xl p-3 sm:p-3.5 flex flex-col space-y-3 min-h-[140px] lg:min-h-[480px]"
              >
                {/* Column Header */}
                <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-slate-200">{col.fullLabel || col.label}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full bg-slate-800 font-mono text-slate-300 text-[10px] font-bold">
                    {colApps.length}
                  </span>
                </div>

                {/* Column Card List */}
                <div className="space-y-2.5 flex-1 overflow-y-auto max-h-[600px] pr-0.5">
                  {colApps.length === 0 ? (
                    <div className="text-[11px] text-slate-600 text-center py-6 sm:py-10">No applications</div>
                  ) : (
                    colApps.map((app) => (
                      <div
                        key={app.application_id || app.id}
                        onClick={() => onSelectApplication(app.application_id || app.job_id_str || app.job_id || app.id?.toString())}
                        className="p-3.5 rounded-lg bg-[#0c1322] border border-slate-800/90 hover:border-blue-500/50 active:scale-[0.99] cursor-pointer transition-all shadow-sm space-y-2.5 group"
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-xs sm:text-sm text-white group-hover:text-blue-300 transition-colors">
                              {app.company}
                            </span>
                            <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-blue-400 transition-colors" />
                          </div>
                          <div className="text-[11px] sm:text-xs text-slate-300 truncate">
                            {app.role}
                          </div>
                        </div>

                        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1.5 border-t border-slate-800/80">
                          <span className="font-medium text-slate-400">
                            {formatSource(app.source)}
                          </span>
                          <span className="px-1.5 py-0.5 rounded font-mono text-[9px] font-semibold bg-blue-500/15 text-blue-300 border border-blue-500/20">
                            {getAppStatus(app)}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
};
