import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Clock, 
  AlertTriangle, 
  Info,
  CheckCircle2,
  Layers,
  Globe
} from 'lucide-react';
import { api } from '../api';
import { formatSource } from '../utils/formatters';

export const AnalyticsView: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAnalytics().then((res) => {
      setData(res);
      setLoading(false);
    }).catch((err) => {
      console.error("Failed to load analytics:", err);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[350px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="glass-panel p-8 rounded-xl text-center text-slate-400">
        <p>No analytics data available.</p>
      </div>
    );
  }

  const funnel = data.funnel ?? {};
  const conversion = data.conversion ?? {};
  const strategyPerformance = data.strategy_performance ?? data.strategy_metrics ?? [];
  const recommendationPerformance = data.recommendation_performance ?? data.recommendation_metrics ?? [];
  const sourcePerformance = data.source_performance ?? data.source_metrics ?? [];
  const responseTimes = data.response_times ?? [];

  return (
    <div className="space-y-4 sm:space-y-6">
      
      {/* Header & Advisory Guardrail Notice */}
      <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-2">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center space-x-2">
            <BarChart3 className="w-5 h-5 text-blue-400" />
            <span>Outcome & Pipeline Analytics</span>
          </h2>
          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/20">
            Advisory Insights
          </span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          Historical patterns inform application strategy and prioritization. Cohorts with <b className="text-slate-200">N &lt; 10</b> are labeled as insufficient sample sizes to ensure statistical reliability.
        </p>
        {!conversion.is_statistically_reliable && conversion.sample_size_warning && (
          <div className="flex items-center space-x-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1.5 rounded-lg">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{conversion.sample_size_warning}</span>
          </div>
        )}
      </div>

      {/* Funnel Metrics & Conversion Rates */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        
        {/* Funnel Counts */}
        <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span>Application Funnel Counts</span>
          </h3>

          <div className="space-y-2.5">
            {[
              { label: 'Discovered Opportunities', count: funnel.discovered ?? 0, rate: null },
              { label: 'Recommended Tier', count: funnel.recommended ?? 0, rate: null },
              { label: 'Prepared Packages', count: funnel.prepared ?? 0, rate: conversion.application_rate ? `${conversion.application_rate}% app` : null },
              { label: 'Submitted Applications', count: funnel.submitted ?? 0, rate: null },
              { label: 'Recruiter Responses', count: funnel.recruiter_responses ?? 0, rate: conversion.response_rate ? `${conversion.response_rate}% resp` : null },
              { label: 'Interviews Scheduled', count: funnel.interviews ?? 0, rate: conversion.interview_rate ? `${conversion.interview_rate}% intv` : null },
              { label: 'Offers Received', count: funnel.offers ?? 0, rate: conversion.offer_rate ? `${conversion.offer_rate}% offer` : null },
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
                  {st.rate && (
                    <span className="text-[11px] font-mono text-blue-400">
                      {st.rate}
                    </span>
                  )}
                  <span className="font-bold text-white text-sm font-mono">{st.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Strategy Cohorts */}
        <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
            <PieChart className="w-4 h-4 text-indigo-400" />
            <span>Resume Strategy Performance</span>
          </h3>

          <div className="space-y-3">
            {strategyPerformance.length === 0 ? (
              <div className="text-xs text-slate-500 py-8 text-center">No strategy cohort data available yet.</div>
            ) : (
              strategyPerformance.map((strat: any, idx: number) => {
                const name = strat.cohort_name || strat.cohort_key || `Strategy ${idx + 1}`;
                const total = strat.total_applications ?? 0;
                const isInsufficient = total < 10;
                return (
                  <div 
                    key={name}
                    className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold font-mono uppercase text-emerald-400">{name}</span>
                      {isInsufficient ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center space-x-1">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Insufficient (N &lt; 10)</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          Sample N={total}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-[11px] font-mono">
                      <div>
                        <span className="text-slate-500">Apps:</span> <b className="text-white">{total}</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Resp:</span> <b className="text-blue-300">{strat.recruiter_responses ?? 0} ({strat.response_rate ?? 0}%)</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Intv:</span> <b className="text-purple-300">{strat.interviews ?? 0} ({strat.interview_rate ?? 0}%)</b>
                      </div>
                      <div>
                        <span className="text-slate-500">Offers:</span> <b className="text-yellow-300">{strat.offers ?? 0} ({strat.offer_rate ?? 0}%)</b>
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
      <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
        <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
          <Globe className="w-4 h-4 text-cyan-400" />
          <span>Source Performance Breakdown</span>
        </h3>
        
        <div className="border border-slate-800 rounded-xl overflow-x-auto">
          <table className="w-full text-left text-xs min-w-[600px]">
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
              {sourcePerformance.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-slate-500">No source outcome data recorded yet.</td>
                </tr>
              ) : (
                sourcePerformance.map((src: any, idx: number) => {
                  const name = src.cohort_name || src.cohort_key || `Source ${idx + 1}`;
                  const total = src.total_applications ?? 0;
                  const isSmall = total < 10;
                  return (
                    <tr key={name} className="hover:bg-slate-900/30">
                      <td className="p-3 font-semibold text-white">{formatSource(name)}</td>
                      <td className="p-3 font-mono">{total}</td>
                      <td className="p-3 font-mono text-blue-300">{src.recruiter_responses ?? 0} ({src.response_rate ?? 0}%)</td>
                      <td className="p-3 font-mono text-purple-300">{src.interviews ?? 0} ({src.interview_rate ?? 0}%)</td>
                      <td className="p-3 font-mono text-yellow-300">{src.offers ?? 0} ({src.offer_rate ?? 0}%)</td>
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
