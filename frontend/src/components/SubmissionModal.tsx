import React, { useState } from 'react';
import { 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle2, 
  X, 
  Send, 
  Lock,
  ExternalLink,
  FileText
} from 'lucide-react';
import { api } from '../api';
import { SubmissionConfirmResponse } from '../types';
import { formatSource } from '../utils/formatters';

interface SubmissionModalProps {
  applicationId: string;
  jobId: string;
  company: string;
  role: string;
  source: string;
  targetUrl?: string;
  strategy: string;
  taskId: string;
  confirmationToken: string;
  onClose: () => void;
  onSuccess: (res: SubmissionConfirmResponse) => void;
}

export const SubmissionModal: React.FC<SubmissionModalProps> = ({
  applicationId,
  jobId,
  company,
  role,
  source,
  targetUrl,
  strategy,
  taskId,
  confirmationToken,
  onClose,
  onSuccess,
}) => {
  const [confirmInput, setConfirmInput] = useState('');
  const [userNotes, setUserNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmissionConfirmResponse | null>(null);

  const isKeywordExact = confirmInput.trim() === 'SUBMIT';

  const handleConfirm = async () => {
    if (!isKeywordExact) return;
    setLoading(true);
    setError(null);

    try {
      const res = await api.confirmSubmission({
        applicationId,
        taskId,
        confirmationToken,
        confirmText: confirmInput.trim(),
        userNotes: userNotes.trim() || undefined,
      });
      setResult(res);
      onSuccess(res);
    } catch (err: any) {
      setError(err.message || 'Submission confirmation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-[#0f172a] border-2 border-rose-500/40 rounded-2xl max-w-xl w-full p-4 sm:p-6 shadow-2xl space-y-4 sm:space-y-5 max-h-[92vh] overflow-y-auto">
        
        {/* Top Warning Banner */}
        <div className="flex items-start justify-between pb-3 sm:pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2 sm:p-2.5 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse shrink-0">
              <ShieldAlert className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
            <div>
              <h3 className="text-sm sm:text-base font-bold text-white uppercase tracking-wide">
                Final Submission Gate
              </h3>
              <p className="text-[11px] sm:text-xs text-rose-300 font-medium">
                Consequential Action: External transmission
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Success State */}
        {result ? (
          <div className="p-5 sm:p-6 rounded-xl bg-blue-950/20 border border-blue-500/30 text-center space-y-4">
            <CheckCircle2 className="w-10 h-10 sm:w-12 sm:h-12 text-blue-400 mx-auto" />
            <h4 className="text-base sm:text-lg font-bold text-white">Submission Authorized — Worker Dispatched</h4>
            <p className="text-xs text-slate-300 max-w-md mx-auto leading-relaxed">
              {result.message}
            </p>
            {result.submission_reference && (
              <div className="inline-block p-2.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-blue-300">
                Authorization Reference: <span className="font-bold">{result.submission_reference}</span>
              </div>
            )}
            <div className="pt-2">
              <button
                onClick={onClose}
                className="w-full sm:w-auto px-5 py-2.5 text-xs sm:text-sm font-semibold bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
              >
                Close & View Progress
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Warning Message */}
            <div className="p-3 sm:p-3.5 rounded-xl bg-rose-950/20 border border-rose-500/30 text-xs text-rose-200 space-y-1">
              <span className="font-bold">You are authorizing external transmission to the employer portal.</span>
              <p className="text-slate-300 text-[11px] leading-relaxed">
                Once confirmed, the browser worker submits verified candidate profile data and answers.
              </p>
            </div>

            {/* Target Summary Card */}
            <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Target Company:</span>
                <span className="font-bold text-white">{company}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Role:</span>
                <span className="font-medium text-slate-200">{role}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Source:</span>
                <span className="font-medium text-slate-200">{formatSource(source)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Resume Strategy:</span>
                <span className="font-mono uppercase text-emerald-400 font-semibold">{strategy}</span>
              </div>
              {targetUrl && (
                <div className="flex items-center justify-between pt-1 border-t border-slate-800/60">
                  <span className="text-slate-400">Portal URL:</span>
                  <a 
                    href={targetUrl} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="text-blue-400 hover:underline flex items-center space-x-1 truncate max-w-[200px] sm:max-w-[280px]"
                  >
                    <span className="truncate">{targetUrl}</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                </div>
              )}
            </div>

            {/* User Notes Input */}
            <div className="space-y-1 text-xs">
              <label className="text-slate-400 font-medium">Optional Submission Notes:</label>
              <input
                type="text"
                placeholder="e.g. Applied with referral / notes"
                value={userNotes}
                onChange={(e) => setUserNotes(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Explicit Gated Confirmation Input */}
            <div className="p-3.5 sm:p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5 sm:space-y-3">
              <label className="text-xs font-semibold text-slate-200 flex items-center space-x-2">
                <Lock className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                <span>Type exact keyword <code className="text-rose-400 font-bold bg-rose-500/10 px-1.5 py-0.5 rounded">SUBMIT</code> to authorize:</span>
              </label>
              
              <input
                type="text"
                placeholder="Type SUBMIT"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm sm:text-base font-mono text-center tracking-widest text-white uppercase focus:outline-none focus:border-rose-500 font-bold"
              />
            </div>

            {/* Error Message */}
            {error && (
              <div className="p-3.5 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-start space-x-2.5 text-xs text-rose-300">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-rose-400" />
                <div className="space-y-0.5">
                  <div className="font-bold text-rose-200">Submission Blocked</div>
                  <div className="text-[11px] leading-relaxed">{error}</div>
                </div>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-2.5 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2.5 text-xs font-medium text-slate-400 hover:text-slate-200 text-center"
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={!isKeywordExact || loading}
                onClick={handleConfirm}
                className={`px-6 py-2.5 text-xs sm:text-sm font-bold rounded-lg transition-all flex items-center justify-center space-x-2 ${
                  isKeywordExact && !loading
                    ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/30'
                    : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                }`}
              >
                <Send className="w-4 h-4" />
                <span>{loading ? 'Validating Token...' : 'Confirm & Authorize Submission'}</span>
              </button>
            </div>
          </>
        )}

      </div>
    </div>
  );
};
