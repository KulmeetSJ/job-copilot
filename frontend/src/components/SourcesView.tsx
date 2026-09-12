import React, { useState, useEffect } from 'react';
import { 
  Globe, 
  ShieldCheck, 
  CheckCircle2, 
  AlertCircle, 
  Lock, 
  Clock, 
  RefreshCw,
  Key
} from 'lucide-react';
import { api } from '../api';
import { SessionMetadataItem, SourceMonitoringItem } from '../types';

export const SourcesView: React.FC = () => {
  const [sources, setSources] = useState<SourceMonitoringItem[]>([]);
  const [sessions, setSessions] = useState<SessionMetadataItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    Promise.all([api.getSources(), api.getSessions()])
      .then(([srcs, sess]) => {
        setSources(srcs);
        setSessions(sess);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-6">
      
      {/* Header & Invariant Notice */}
      <div className="glass-panel p-5 rounded-xl space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <Globe className="w-5 h-5 text-blue-400" />
            <span>Job Sources & Authenticated Sessions (Phase 10C)</span>
          </h2>
          <button
            onClick={loadData}
            className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
        <p className="text-xs text-slate-400">
          Source adapters allow authenticated form inspection. In accordance with Phase 10C security invariants, <b className="text-slate-200">zero passwords, cookies, or storage tokens</b> are exposed to the UI or API.
        </p>
      </div>

      {/* Configured Sources Table */}
      <div className="glass-panel p-5 rounded-xl space-y-4">
        <h3 className="text-sm font-semibold text-white">Configured Job Sources</h3>

        <div className="border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold">
              <tr>
                <th className="p-3">Source Name</th>
                <th className="p-3">Discovery Mode</th>
                <th className="p-3">Health Status</th>
                <th className="p-3">Login Requirement</th>
                <th className="p-3">Active Session</th>
                <th className="p-3">Last Run</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
              {sources.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-slate-500">No sources configured.</td>
                </tr>
              ) : (
                sources.map((src) => (
                  <tr key={src.source_name} className="hover:bg-slate-900/30">
                    <td className="p-3 font-semibold text-white">
                      <div>{src.display_name}</div>
                      <span className="text-[10px] text-slate-500 font-mono">{src.source_name}</span>
                    </td>
                    <td className="p-3 font-mono text-slate-300 uppercase">{src.discovery_mode}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                        src.health_status === 'HEALTHY' 
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                      }`}>
                        {src.health_status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-400">
                      {src.requires_login ? 'Auth Required' : 'Public Feed'}
                    </td>
                    <td className="p-3 font-mono">
                      {src.has_active_session ? (
                        <span className="text-emerald-400 font-semibold">✓ Active</span>
                      ) : (
                        <span className="text-slate-500">None</span>
                      )}
                    </td>
                    <td className="p-3 font-mono text-slate-500">
                      {src.last_run_at ? new Date(src.last_run_at).toLocaleString() : 'Never'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Authenticated Sessions Metadata Table (Zero Secrets) */}
      <div className="glass-panel p-5 rounded-xl space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-indigo-400" />
            <span>Authenticated Browser Sessions Metadata</span>
          </h3>
          <span className="text-[11px] text-slate-500 font-mono">Zero cookie / token exposure</span>
        </div>

        <div className="border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold">
              <tr>
                <th className="p-3">Session ID</th>
                <th className="p-3">Source</th>
                <th className="p-3">Status</th>
                <th className="p-3">Storage State</th>
                <th className="p-3">Created</th>
                <th className="p-3">Expires</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
              {sessions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-slate-500">No active authenticated browser sessions.</td>
                </tr>
              ) : (
                sessions.map((sess) => (
                  <tr key={sess.session_id} className="hover:bg-slate-900/30">
                    <td className="p-3 font-mono text-blue-400">{sess.session_id}</td>
                    <td className="p-3 capitalize font-semibold text-white">{sess.source}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        {sess.status}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-slate-400">
                      {sess.has_stored_state ? 'Encrypted on disk (0600)' : 'Not initialized'}
                    </td>
                    <td className="p-3 font-mono text-slate-500">
                      {new Date(sess.created_at).toLocaleDateString()}
                    </td>
                    <td className="p-3 font-mono text-slate-500">
                      {sess.expires_at ? new Date(sess.expires_at).toLocaleDateString() : 'N/A'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
};
