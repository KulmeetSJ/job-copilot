import React, { useState } from 'react';
import { 
  Laptop, 
  Key, 
  Copy, 
  Check, 
  Clock, 
  ShieldAlert, 
  X,
  Terminal,
  ExternalLink
} from 'lucide-react';
import { api } from '../api';
import { PairingCodeResponse } from '../types';

interface DeviceSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPaired?: () => void;
}

export const DeviceSettingsModal: React.FC<DeviceSettingsModalProps> = ({ isOpen, onClose, onPaired }) => {
  const [loading, setLoading] = useState(false);
  const [pairingData, setPairingData] = useState<PairingCodeResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleGenerateCode = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.generatePairingCode('Local Interactive Machine');
      setPairingData(data);
      if (onPaired) onPaired();
    } catch (err: any) {
      setError(err.message || 'Failed to generate pairing code');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-700 bg-slate-900/95 shadow-2xl space-y-5 text-left">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Laptop className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">Connect Local Browser Agent</h3>
              <p className="text-xs text-slate-400">Run interactive browser tasks on your machine with zero cloud cost</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Security & Interactive Invariant Banner */}
        <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 rounded-xl space-y-1.5 text-xs text-blue-200">
          <div className="font-semibold flex items-center space-x-1.5 text-blue-300">
            <ShieldAlert className="w-4 h-4 text-blue-400" />
            <span>Interactive Same-Session Guarantee</span>
          </div>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            When CAPTCHA, Login, or MFA is encountered, the local agent keeps the <strong>same visible browser window open</strong> for you to complete. Your credentials and cookies never leave your machine.
          </p>
        </div>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-300">
            {error}
          </div>
        )}

        {!pairingData ? (
          <div className="text-center py-4 space-y-4">
            <p className="text-xs text-slate-300">
              Generate a short-lived 6-digit pairing code to securely pair your laptop or desktop with this Job Copilot dashboard.
            </p>
            <button
              onClick={handleGenerateCode}
              disabled={loading}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-500/20 transition-all flex items-center justify-center space-x-2 mx-auto disabled:opacity-50"
            >
              <Key className="w-4 h-4" />
              <span>{loading ? 'Generating Code...' : 'Generate 6-Digit Pairing Code'}</span>
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Pairing Code Display */}
            <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl text-center space-y-2">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">One-Time Pairing Code</span>
              <div className="text-3xl font-mono font-black tracking-widest text-emerald-400">
                {pairingData.pairing_code}
              </div>
              <div className="flex items-center justify-center space-x-2 text-[10px] text-slate-400">
                <span className="flex items-center space-x-1">
                  <Clock className="w-3 h-3 text-amber-400" />
                  <span>Expires in 10 minutes</span>
                </span>
                {pairingData.server_url && (
                  <>
                    <span>•</span>
                    <span className="text-blue-400 font-mono">{pairingData.server_url}</span>
                  </>
                )}
              </div>
            </div>

            {/* CLI Command */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                <Terminal className="w-3.5 h-3.5 text-blue-400" />
                <span>Run this command in your terminal:</span>
              </label>
              <div className="flex items-center justify-between p-3 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-slate-200">
                <code className="text-blue-300 select-all overflow-x-auto">{pairingData.cli_command}</code>
                <button
                  onClick={() => copyToClipboard(pairingData.cli_command)}
                  className="ml-2 p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors flex items-center space-x-1 shrink-0"
                  title="Copy command"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span className="text-[10px]">{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            <div className="p-3 bg-slate-800/40 rounded-xl space-y-1 text-[11px] text-slate-400">
              <div className="font-semibold text-slate-300">Next Steps:</div>
              <div>1. Run the command above on your computer.</div>
              <div>2. Start the local agent: <code className="text-slate-200 font-mono">python -m job_copilot.browser_agent start</code></div>
              <div>3. Automation tasks will automatically run on your local machine!</div>
            </div>

            <button
              onClick={handleGenerateCode}
              disabled={loading}
              className="text-xs text-slate-400 hover:text-slate-200 underline block mx-auto pt-1"
            >
              Generate a new code
            </button>
          </div>
        )}

        {/* Modal Footer */}
        <div className="pt-2 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-xl transition-colors"
          >
            Done
          </button>
        </div>

      </div>
    </div>
  );
};
