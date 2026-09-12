import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Clock, 
  AlertTriangle, 
  Info,
  CheckCircle2
} from 'lucide-react';
import { api } from '../api';

export const AnalyticsView: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAnalytics().then((res) => {
      setData(res);
      setLoading(false);
    });
  }, []);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center min-h-[350px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const { funnel, conversion, strategy_metrics, recommendation_metrics, source_metrics, response_times } = data;

  return (
    <div className="space-y-6">
      
      {/* Header & Advisory Guardrail Notice */}
      <div className="glass-panel p-5 rounded-xl space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <BarChart3 className="w-5 h-5 text-blue-400" />
            <span>Outcome & Pipeline Analytics (Phase 8)</span>
          </h2>
          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/20">
            Advisory Learning Only
          </span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          Historical patterns inform application strategy and prioritization. In accordance with Phase 8 safety invariants, samples with <b className="text-slate-200">N &lt; 10</b> are labeled as insufficient samples and never used for ungrounded conclusions.
        </p>
      </div>

      {/* Funnel Metrics & Conversion Rates */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Funnel Counts */}
        <div className="glass-panel p-5 rounded-xl space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span>Application Conversion Funnel</span>
          </h3>

          <div className="space-y-2.5">
            {[
              { label: 'Discovered Opportunities', count: funnel.discovered, rate: null },
              { label: 'Recommended Tier', count: funnel.recommended, rate: conversion.discovered_to_recommended },
              { label: 'Prepared Packages', count: funnel.prepared, rate: conversion.recommended_to_prepared },
              { label: 'Submitted Applications', count: funnel.submitted, rate: conversion.prepared_to_submitted },
              { label: 'Recruiter Responses', count: funnel.recruiter_responses, rate: conversion.submitted_to_response },
              { label: 'Interviews Scheduled', count: funnel.interviews, rate: conversion.response_to_interview },
              { label: 'Offers Received', count: funnel.offers, rate: conversion.interview_to_offer },
            ].map((st, i) => (
              <div 
                key={i}
                className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs"
              >
                <div className="flex items-center space-x-2">
                  <span className="w-5 h-5 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center font-mono text-[10px]">
                    {i + 1}
                  </span>
                  <span className="text-slate-200 font-medium">{st.label}</span>
                </div>
                
                <div className="flex items-center space-x-4">
                  {st.rate !== null && (
                    <span className="text-[11px] font-mono text-blue-400">
                      {st.rate}% conv
                    </span>
                  )}
                  <span className="font-bold text-white text-sm font-mono">{st.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Strategy Cohorts */}
        <div className="glass-panel p-5 rounded-xl space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <PieChart className="w-4 h-4 text-indigo-400" />
            <span>Resume Strategy Performance</span>
          </h3>

          <div className="space-y-3">
            {strategy_metrics.length === 0 ? (
              <div className="text-xs text-slate-500 py-8 text-center">No strategy cohort data available yet.</div>
            ) : (
              strategy_metrics.map((strat: any) => {
                const isInsufficient = strat.total_applications < 10;
                return (
                  <div 
                    key={strat.cohort_key}
                    className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold font-mono uppercase text-emerald-400">{strat.cohort_key}</span>
                      {isInsufficient ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center space-x-1">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Insufficient sample (N &lt; 10)</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          Sample N={strat.total_applications}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-4 gap-2 pt-1 text-[11px] font-mono">
                      <div>
                        <span className="text-slate-500">Apps:</span> <b className="text-white">{strat.total_applications}</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Resp:</span> <b className="text-blue-300">{strat.recruiter_responses} ({strat.response_rate}%)</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Intv:</span> <b className="text-purple-300">{strat.interviews} ({strat.interview_rate}%)</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Offers:</span> <b className="text-yellow-300">{strat.offers} ({strat.offer_rate}%)</b>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

      </div>

      {/* Sources Performance Breakdown */}
      <div className="glass-panel p-5 rounded-xl space-y-4">
        <h3 className="text-sm font-semibold text-white">Source Performance Breakdown</h3>
        
        <div className="border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold">
              <tr>
                <th className="p-3">Job Source</th>
                <th className="p-3">Total Applications</th>
                <th className="p-3">Recruiter Responses</th>
                <th className="p-3">Interviews</th>
                <th className="p-3">Offers</th>
                <th className="p-3">Reliability Assessment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
              {source_metrics.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-slate-500">No source outcome data recorded yet.</td>
                </tr>
              ) : (
                source_metrics.map((src: any) => {
                  const isSmall = src.total_applications < 10;
                  return (
                    <tr key={src.cohort_key} className="hover:bg-slate-900/30">
                      <td className="p-3 font-semibold capitalize text-white">{src.cohort_key}</td>
                      <td className="p-3 font-mono">{src.total_applications}</td>
                      <td className="p-3 font-mono text-blue-300">{src.recruiter_responses} ({src.response_rate}%)</td>
                      <td className="p-3 font-mono text-purple-300">{src.interviews} ({src.interview_rate}%)</td>
                      <td className="p-3 font-mono text-yellow-300">{src.offers} ({src.offer_rate}%)</td>
                      <td className="p-3">
                        {isSmall ? (
                          <span className="text-[10px] text-amber-400 font-medium">Insufficient sample (N &lt; 10)</span>
                        ) : (
                          <span className="text-[10px] text-emerald-400 font-medium">Statistically reliable (N &ge; 10)</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
};
