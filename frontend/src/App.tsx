import React, { useState, useEffect } from 'react';
import { api } from './api';
import { 
  DashboardOverviewResponse, 
  DashboardQueueItem, 
  PriorityBand, 
  QueueStatus 
} from './types';
import { Header } from './components/Header';
import { OverviewView } from './components/OverviewView';
import { QueueView } from './components/QueueView';
import { JobDetailModal } from './components/JobDetailModal';
import { ApplicationReviewView } from './components/ApplicationReviewView';
import { TrackingView } from './components/TrackingView';
import { AnalyticsView } from './components/AnalyticsView';
import { SourcesView } from './components/SourcesView';
import { ActivityView } from './components/ActivityView';

export function App() {
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [queueItems, setQueueItems] = useState<DashboardQueueItem[]>([]);
  const [queueLoading, setQueueLoading] = useState(false);
  
  // Filter state for Queue
  const [selectedStatus, setSelectedStatus] = useState<QueueStatus | undefined>(undefined);
  const [selectedPriority, setSelectedPriority] = useState<PriorityBand | undefined>(undefined);
  const [minScore, setMinScore] = useState<number>(0);

  // Selected entities
  const [inspectJobId, setInspectJobId] = useState<string | null>(null);
  const [activeAppId, setActiveAppId] = useState<string | undefined>(undefined);

  const loadOverview = () => {
    api.getOverview().then(setOverview).catch(console.error);
  };

  const loadQueue = () => {
    setQueueLoading(true);
    api.getQueue({
      status: selectedStatus,
      priority: selectedPriority,
      min_score: minScore > 0 ? minScore : undefined,
    })
      .then((res) => {
        setQueueItems(res.items);
        setQueueLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setQueueLoading(false);
      });
  };

  useEffect(() => {
    loadOverview();
    const interval = setInterval(loadOverview, 30000); // 30s poll
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === 'queue') {
      loadQueue();
    }
  }, [activeTab, selectedStatus, selectedPriority, minScore]);

  const handlePrepareJob = async (jobId: string) => {
    try {
      await api.prepareApplication(jobId);
      loadOverview();
      loadQueue();
      setActiveAppId(jobId);
      setActiveTab('applications');
    } catch (err) {
      console.error(err);
    }
  };

  const handleSkipJob = async (jobId: string) => {
    try {
      await api.skipApplication(jobId, 'Skipped from priority queue');
      loadOverview();
      loadQueue();
    } catch (err) {
      console.error(err);
    }
  };

  const handleReviewApp = (appId: string) => {
    setActiveAppId(appId);
    setActiveTab('applications');
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col selection:bg-blue-500 selection:text-white">
      
      {/* Shell Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        readyForReviewCount={overview?.pipeline_counts.ready_for_review || 0}
        needsInputCount={overview?.pipeline_counts.needs_user_input || 0}
      />

      {/* Main View Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && (
          <OverviewView
            overview={overview}
            onNavigateTab={setActiveTab}
            onSelectJob={(id) => setInspectJobId(id)}
          />
        )}

        {activeTab === 'queue' && (
          <QueueView
            items={queueItems}
            loading={queueLoading}
            onRefresh={loadQueue}
            onInspectJob={(id) => setInspectJobId(id)}
            onPrepareJob={handlePrepareJob}
            onReviewApplication={handleReviewApp}
            onSkipJob={handleSkipJob}
            selectedStatus={selectedStatus}
            setSelectedStatus={setSelectedStatus}
            selectedPriority={selectedPriority}
            setSelectedPriority={setSelectedPriority}
            minScore={minScore}
            setMinScore={setMinScore}
          />
        )}

        {activeTab === 'applications' && (
          <ApplicationReviewView
            initialApplicationId={activeAppId}
            onNavigateTab={setActiveTab}
          />
        )}

        {activeTab === 'tracking' && (
          <TrackingView
            onSelectApplication={handleReviewApp}
          />
        )}

        {activeTab === 'analytics' && (
          <AnalyticsView />
        )}

        {activeTab === 'sources' && (
          <SourcesView />
        )}

        {activeTab === 'activity' && (
          <ActivityView />
        )}
      </main>

      {/* Job Detail & Match Explanation Modal */}
      {inspectJobId && (
        <JobDetailModal
          jobId={inspectJobId}
          onClose={() => setInspectJobId(null)}
          onPrepare={handlePrepareJob}
          onReview={handleReviewApp}
        />
      )}

      {/* Global Footer */}
      <footer className="border-t border-slate-800/80 bg-[#070a10] py-6 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-slate-400">Job Copilot</span>
            <span>•</span>
            <span>Phase 11 Human Review Dashboard</span>
          </div>
          <div className="font-mono text-[11px] text-slate-600">
            Authoritative Pipeline Locked • Confirmation Gate Protected • Zero Autonomous Submit
          </div>
        </div>
      </footer>

    </div>
  );
}

export default App;
