import React, { useState } from 'react';
import { 
  Briefcase, 
  Layers, 
  CheckCircle2, 
  BarChart3, 
  Globe, 
  ShieldCheck, 
  Activity, 
  Key, 
  AlertTriangle,
  Menu,
  X
} from 'lucide-react';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  readyForReviewCount: number;
  needsInputCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  readyForReviewCount,
  needsInputCount,
}) => {
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [apiKey, setApiKey] = useState(localStorage.getItem('copilot_api_key') || '');

  const saveApiKey = () => {
    if (apiKey.trim()) {
      localStorage.setItem('copilot_api_key', apiKey.trim());
    } else {
      localStorage.removeItem('copilot_api_key');
    }
    setShowKeyModal(false);
    window.location.reload();
  };

  const navItems = [
    { id: 'overview', label: 'Overview', icon: Layers },
    { id: 'queue', label: 'Priority Queue', icon: Briefcase },
    { 
      id: 'applications', 
      label: 'Application Review', 
      icon: CheckCircle2,
      badge: readyForReviewCount > 0 ? readyForReviewCount : undefined,
      badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    },
    { id: 'tracking', label: 'Tracking Pipeline', icon: Activity },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'sources', label: 'Sources & Sessions', icon: Globe },
    { id: 'activity', label: 'Audit Log', icon: ShieldCheck },
  ];

  return (
    <>
      <header className="border-b border-slate-800 bg-[#0c121e]/95 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            
            {/* Branding */}
            <div className="flex items-center space-x-2.5 sm:space-x-3">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20 ring-1 ring-white/20 shrink-0">
                <Briefcase className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
              </div>
              <div>
                <div className="flex items-center space-x-1.5 sm:space-x-2">
                  <span className="font-bold text-base sm:text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-blue-300 bg-clip-text text-transparent">
                    Job Copilot
                  </span>
                  <span className="px-1.5 py-0.2 text-[9px] sm:text-[10px] font-semibold tracking-wide uppercase rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    Phase 11
                  </span>
                </div>
                <p className="text-[10px] sm:text-xs text-slate-400 font-medium truncate max-w-[190px] sm:max-w-none">
                  Human Review & Control Center
                </p>
              </div>
            </div>

            {/* Desktop Navigation Tabs */}
            <nav className="hidden lg:flex space-x-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveTab(item.id)}
                    className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      isActive
                        ? 'bg-blue-600/15 text-blue-400 border border-blue-500/30 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{item.label}</span>
                    {item.badge !== undefined && (
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full border font-mono font-semibold ${item.badgeColor}`}>
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>

            {/* Right Controls */}
            <div className="flex items-center space-x-2">
              {needsInputCount > 0 && (
                <div className="hidden sm:flex items-center space-x-1 px-2 py-1 rounded-full bg-rose-500/15 border border-rose-500/30 text-rose-300 text-[11px] font-medium animate-pulse">
                  <AlertTriangle className="w-3 h-3" />
                  <span>{needsInputCount} Input</span>
                </div>
              )}
              
              <button
                onClick={() => setShowKeyModal(true)}
                title="API Authentication Key"
                className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition-colors border border-slate-800"
              >
                <Key className="w-4 h-4" />
              </button>

              {/* Mobile Menu Toggle Button */}
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label="Toggle navigation menu"
                className="lg:hidden p-2 rounded-lg text-slate-300 hover:text-white bg-slate-900 border border-slate-800"
              >
                {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
            </div>

          </div>

          {/* Mobile Horizontal Navigation Strip */}
          <div className="lg:hidden flex items-center space-x-1.5 overflow-x-auto py-2 border-t border-slate-800/60 scrollbar-none no-scrollbar -mx-3 px-3">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    setMobileMenuOpen(false);
                  }}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap font-medium transition-all shrink-0 ${
                    isActive
                      ? 'bg-blue-600 text-white font-semibold shadow-sm'
                      : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                  {item.badge !== undefined && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-amber-400/20 text-amber-300 font-mono font-bold">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Mobile Dropdown Drawer */}
          {mobileMenuOpen && (
            <div className="lg:hidden py-3 px-1 border-t border-slate-800 space-y-1 bg-[#090d16] rounded-b-xl shadow-2xl">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setActiveTab(item.id);
                      setMobileMenuOpen(false);
                    }}
                    className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                      isActive
                        ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30 font-semibold'
                        : 'text-slate-300 hover:bg-slate-800/60'
                    }`}
                  >
                    <div className="flex items-center space-x-2.5">
                      <Icon className="w-4 h-4 text-blue-400" />
                      <span>{item.label}</span>
                    </div>
                    {item.badge !== undefined && (
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-mono font-semibold ${item.badgeColor}`}>
                        {item.badge} review
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

        </div>
      </header>

      {/* API Key Modal */}
      {showKeyModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0f172a] border border-slate-700 rounded-xl max-w-md w-full p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white mb-2 flex items-center space-x-2">
              <Key className="w-5 h-5 text-blue-400" />
              <span>Dashboard Access Key</span>
            </h3>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              If your deployed Job Copilot backend requires an API key (<code className="text-blue-300">DASHBOARD_API_KEY</code>), enter it here. In local development with default settings, this can remain blank.
            </p>
            <input
              type="password"
              placeholder="Enter API Key (optional)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-blue-500 mb-4"
            />
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setShowKeyModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={saveApiKey}
                className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
              >
                Save Key
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
