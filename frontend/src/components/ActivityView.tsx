import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  Clock, 
  Search, 
  RefreshCw, 
  Filter 
} from 'lucide-react';
import { api } from '../api';

export const ActivityView: React.FC = () => {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');

  const loadActivity = () => {
    setLoading(true);
    api.getActivity(100)
      .then((data) => {
        setEvents(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadActivity();
  }, []);

  const filtered = events.filter((e) => {
    if (!searchFilter) return true;
    const q = searchFilter.toLowerCase();
    return `${e.event_type} ${e.application_id} ${e.job_id} ${e.notes || ''}`.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="glass-panel p-5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <ShieldCheck className="w-5 h-5 text-blue-400" />
            <span>System Activity & Sanitized Audit Log</span>
          </h2>
          <p className="text-xs text-slate-400">
            Append-only chronological audit trail. Internal tokens and candidate credentials are never logged or exposed.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          <input
            type="text"
            placeholder="Filter event stream..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="w-full md:w-64 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
          />

          <button
            onClick={loadActivity}
            className="p-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Events Table / Stream */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="glass-panel rounded-xl overflow-hidden border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold">
              <tr>
                <th className="p-3">Timestamp</th>
                <th className="p-3">Event Type</th>
                <th className="p-3">Target Entity</th>
                <th className="p-3">Source Operator</th>
                <th className="p-3">Audit Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-slate-500">No activity events found.</td>
                </tr>
              ) : (
                filtered.map((evt) => (
                  <tr key={evt.event_id} className="hover:bg-slate-900/30">
                    <td className="p-3 font-mono text-slate-500 whitespace-nowrap">
                      {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : ''}
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/20">
                        {evt.event_type}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-slate-300">
                      {evt.application_id || evt.job_id || 'SYSTEM'}
                    </td>
                    <td className="p-3 font-mono text-slate-400">
                      {evt.source}
                    </td>
                    <td className="p-3 text-slate-300">
                      {evt.notes || '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
};
