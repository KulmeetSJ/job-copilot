import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  Search, 
  ExternalLink, 
  Clock, 
  ChevronRight, 
  CheckCircle, 
  AlertCircle 
} from 'lucide-react';
import { api } from '../api';

interface TrackingViewProps {
  onSelectApplication: (applicationId: string) => void;
}

export const TrackingView: React.FC<TrackingViewProps> = ({ onSelectApplication }) => {
  const [applications, setApplications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterQuery, setFilterQuery] = useState('');

  useEffect(() => {
    api.listApplications().then((data) => {
      setApplications(data);
      setLoading(false);
    });
  }, []);

  const columns = [
    { id: 'DISCOVERED', label: 'Discovered & Recommended', statuses: ['DISCOVERED', 'RECOMMENDED'] },
    { id: 'PREPARED', label: 'Prepared & Review', statuses: ['PREPARED', 'READY_FOR_REVIEW', 'WAITING_FOR_USER'] },
    { id: 'SUBMITTED', label: 'Submitted & Sent', statuses: ['SUBMITTED', 'APPLIED', 'ACKNOWLEDGED'] },
    { id: 'IN_PROGRESS', label: 'Response & Assessment', statuses: ['RECRUITER_RESPONSE', 'ASSESSMENT'] },
    { id: 'INTERVIEW', label: 'Interviewing', statuses: ['INTERVIEW', 'FINAL_ROUND'] },
    { id: 'OFFER', label: 'Offer & Decision', statuses: ['OFFER', 'ACCEPTED'] },
    { id: 'ARCHIVED', label: 'Closed / Rejected', statuses: ['REJECTED', 'WITHDRAWN', 'EXPIRED', 'CLOSED'] },
  ];

  const filtered = applications.filter((app) => {
    if (!filterQuery) return true;
    const q = filterQuery.toLowerCase();
    return `${app.company} ${app.role} ${app.status}`.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="glass-panel p-5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <Activity className="w-5 h-5 text-blue-400" />
            <span>Phase 8 Application Lifecycle Tracking</span>
          </h2>
          <p className="text-xs text-slate-400">
            Append-only application ledger across all 16 authoritative status milestones.
          </p>
        </div>

        <div className="w-full md:w-64">
          <input
            type="text"
            placeholder="Filter applications..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Kanban Board */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3.5 overflow-x-auto min-w-[1000px] pb-4">
          {columns.map((col) => {
            const colApps = filtered.filter((a) => col.statuses.includes(a.status));
            return (
              <div 
                key={col.id}
                className="bg-slate-900/40 border border-slate-800 rounded-xl p-3 flex flex-col space-y-3 min-h-[450px]"
              >
                <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs">
                  <span className="font-semibold text-slate-300">{col.label}</span>
                  <span className="px-1.5 py-0.5 rounded-full bg-slate-800 font-mono text-slate-400 text-[10px]">
                    {colApps.length}
                  </span>
                </div>

                <div className="space-y-2.5 flex-1 overflow-y-auto max-h-[550px] pr-1">
                  {colApps.length === 0 ? (
                    <div className="text-[11px] text-slate-600 text-center py-8">Empty</div>
                  ) : (
                    colApps.map((app) => (
                      <div
                        key={app.application_id || app.id}
                        onClick={() => onSelectApplication(app.application_id || app.job_id_str || app.id.toString())}
                        className="p-3 rounded-lg bg-[#0c1322] border border-slate-800 hover:border-blue-500/40 cursor-pointer transition-all shadow-sm space-y-2"
                      >
                        <div className="space-y-0.5">
                          <div className="font-bold text-xs text-white hover:text-blue-300">
                            {app.company}
                          </div>
                          <div className="text-[11px] text-slate-300 truncate">
                            {app.role}
                          </div>
                        </div>

                        <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                          <span className="capitalize">{app.source}</span>
                          <span className="px-1.5 py-0.2 rounded font-mono text-[9px] bg-blue-500/10 text-blue-300">
                            {app.status}
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
