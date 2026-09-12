import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  HelpCircle, 
  Eye, 
  Clock, 
  Send, 
  Download, 
  Copy, 
  Sparkles, 
  Layers, 
  ShieldCheck, 
  ShieldAlert,
  Save,
  Check,
  FileCode,
  ExternalLink,
  ChevronDown,
  Loader2,
  Play,
} from 'lucide-react';
import { api } from '../api';
import { ApplicationDetailResponse } from '../types';
import { SubmissionModal } from './SubmissionModal';
import { formatSource } from '../utils/formatters';

interface ApplicationReviewViewProps {
  initialApplicationId?: string;
  onNavigateTab: (tab: string) => void;
}

export const ApplicationReviewView: React.FC<ApplicationReviewViewProps> = ({
  initialApplicationId,
  onNavigateTab,
}) => {
  const [applications, setApplications] = useState<any[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<string>(initialApplicationId || '');
  const [detail, setDetail] = useState<ApplicationDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState<'resume' | 'answers' | 'human_input' | 'browser' | 'timeline'>('resume');
  const [resumeViewMode, setResumeViewMode] = useState<'pdf' | 'latex'>('pdf');
  const [copiedTex, setCopiedTex] = useState(false);
  const [copiedCover, setCopiedCover] = useState(false);
  
  // Human Input form state
  const [humanAnswers, setHumanAnswers] = useState<Record<string, string>>({});
  const [savingInputs, setSavingInputs] = useState(false);
  const [inputSavedMsg, setInputSavedMsg] = useState(false);
  const [resuming, setResuming] = useState(false);

  // Submission Modal state
  const [showSubmissionModal, setShowSubmissionModal] = useState(false);

  // Retry Submission Modal state
  const [showRetryModal, setShowRetryModal] = useState(false);
  const [retryAcknowledged, setRetryAcknowledged] = useState(false);
  const [retryNotes, setRetryNotes] = useState('');
  const [retrying, setRetrying] = useState(false);

  const [listLoading, setListLoading] = useState(true);

  // Authenticated PDF and Screenshot Blob URLs
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [screenshotBlobUrl, setScreenshotBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    if (detail?.application_id && resumeViewMode === 'pdf') {
      setPdfLoading(true);
      api.fetchBlobUrl(`/api/dashboard/applications/${detail.application_id}/resume/pdf`)
        .then(url => {
          if (active) {
            createdUrl = url;
            setPdfBlobUrl(url);
          } else {
            URL.revokeObjectURL(url);
          }
        })
        .catch(err => {
          console.error('Failed to load resume PDF:', err);
          if (active) setPdfBlobUrl(null);
        })
        .finally(() => {
          if (active) setPdfLoading(false);
        });
    }
    return () => {
      active = false;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [detail?.application_id, resumeViewMode]);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    if (detail?.browser_review?.screenshot_artifact_id) {
      api.fetchBlobUrl(`/api/dashboard/artifacts/${detail.browser_review.screenshot_artifact_id}/content`)
        .then(url => {
          if (active) {
            createdUrl = url;
            setScreenshotBlobUrl(url);
          } else {
            URL.revokeObjectURL(url);
          }
        })
        .catch(err => {
          console.error('Failed to load screenshot:', err);
          if (active) setScreenshotBlobUrl(null);
        });
    }
    return () => {
      active = false;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [detail?.browser_review?.screenshot_artifact_id]);

  const handleDownloadPdf = async () => {
    if (!detail?.application_id) return;
    try {
      setDownloadingPdf(true);
      const cleanCompany = (detail.company || 'Company').replace(/[^a-zA-Z0-9_-]/g, '_');
      const cleanRole = (detail.role || 'Software_Engineer').replace(/[^a-zA-Z0-9_-]/g, '_');
      const filename = `Kulmeet_Singh_${cleanCompany}_${cleanRole}.pdf`;
      await api.downloadFile(
        `/api/dashboard/applications/${detail.application_id}/resume/pdf`,
        filename
      );
    } catch (err: any) {
      alert(err.message || 'Failed to download resume PDF');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const handleRetrySubmit = async () => {
    if (!detail?.application_id || !retryAcknowledged) return;
    try {
      setRetrying(true);
      const updated = await api.retryApplication(detail.application_id, {
        acknowledge_duplicate_risk: true,
        user_notes: retryNotes || 'User acknowledged duplicate risk and authorized retry review.',
      });
      setDetail(updated);
      setShowRetryModal(false);
      setRetryAcknowledged(false);
      setRetryNotes('');
    } catch (err: any) {
      alert(err.message || 'Failed to initialize retry');
    } finally {
      setRetrying(false);
    }
  };

  const handleOpenPdf = async () => {
    if (!detail?.application_id) return;
    try {
      const url = await api.fetchBlobUrl(`/api/dashboard/applications/${detail.application_id}/resume/pdf`);
      window.open(url, '_blank');
    } catch (err: any) {
      alert(err.message || 'Failed to open resume PDF');
    }
  };

  // Load application list
  useEffect(() => {
    setListLoading(true);
    api.listApplications()
      .then((apps) => {
        setApplications(apps);
        if (!selectedAppId && apps.length > 0) {
          setSelectedAppId(apps[0].application_id || apps[0].job_id_str || apps[0].id.toString());
        }
        setListLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setListLoading(false);
      });
  }, []);

  // Update selected app if prop changes
  useEffect(() => {
    if (initialApplicationId) {
      setSelectedAppId(initialApplicationId);
    }
  }, [initialApplicationId]);

  // Load application detail
  useEffect(() => {
    if (!selectedAppId) return;
    setLoading(true);
    api.getApplicationDetail(selectedAppId)
      .then((data) => {
        setDetail(data);
        // Prepopulate human answers if empty
        const initialMap: Record<string, string> = {};
        data.user_inputs_required.forEach((u) => {
          initialMap[u.question_id] = u.current_value || '';
        });
        setHumanAnswers(initialMap);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [selectedAppId]);

  const handleCopyTex = () => {
    if (detail?.resume_tex_content) {
      navigator.clipboard.writeText(detail.resume_tex_content);
      setCopiedTex(true);
      setTimeout(() => setCopiedTex(false), 2000);
    }
  };

  const handleCopyCover = () => {
    if (detail?.cover_letter_text) {
      navigator.clipboard.writeText(detail.cover_letter_text);
      setCopiedCover(true);
      setTimeout(() => setCopiedCover(false), 2000);
    }
  };

  const handleSaveInputs = async () => {
    if (!detail) return;
    setSavingInputs(true);
    setInputSavedMsg(false);

    const payload = detail.user_inputs_required.map((u) => ({
      question_id: u.question_id,
      question_text: u.question_text,
      answer_value: humanAnswers[u.question_id] || '',
    }));

    try {
      const updated = await api.submitHumanInput(detail.application_id, payload);
      setDetail(updated);
      setInputSavedMsg(true);
      setTimeout(() => setInputSavedMsg(false), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setSavingInputs(false);
    }
  };

  const handlePrepareAgain = async () => {
    if (!detail) return;
    setLoading(true);
    try {
      const updated = await api.prepareApplication(detail.application_id);
      setDetail(updated);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async () => {
    if (!detail) return;
    setResuming(true);
    try {
      const updated = await api.resumeApplication(detail.application_id);
      setDetail(updated);
    } catch (err) {
      console.error('Failed to resume automation:', err);
    } finally {
      setResuming(false);
    }
  };

  // Compute canonical status
  const taskStatus = detail?.browser_review?.status || detail?.status || 'DISCOVERED';
  const isBlockerActive = Boolean(
    detail?.blocker_type || 
    ['CAPTCHA_REQUIRED', 'LOGIN_REQUIRED', 'MFA_REQUIRED', 'HUMAN_ACTION_REQUIRED', 'USER_INPUT_REQUIRED'].includes(taskStatus)
  );
  const isReadyToConfirm = taskStatus === 'READY_FOR_REVIEW' || detail?.status === 'READY_TO_APPLY';
  const isSubmissionAuthorized = taskStatus === 'SUBMISSION_AUTHORIZED';
  const isSubmissionRunning = taskStatus === 'SUBMISSION_RUNNING' || taskStatus === 'RUNNING';
  const isSubmitted = detail?.status === 'APPLIED' || taskStatus === 'COMPLETED';
  const isUnverified = detail?.is_external_unverified || taskStatus === 'SUBMISSION_UNVERIFIED';

  return (
    <div className="space-y-4 sm:space-y-6">
      
      {/* Top Application Selector & Summary */}
      <div className="glass-panel p-4 sm:p-5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
        <div className="space-y-1 w-full md:w-auto">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
              Application Review & Materials
            </h2>
            {detail?.status && (
              <span className={`px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-semibold uppercase ${
                isBlockerActive
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse'
                  : isReadyToConfirm
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse'
                  : isSubmissionAuthorized || isSubmissionRunning
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 animate-pulse'
                  : isSubmitted && !isUnverified
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : isUnverified
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'bg-slate-700/50 text-slate-300 border border-slate-600'
              }`}>
                {isBlockerActive ? (detail.blocker_type ? `${detail.blocker_type} REQUIRED` : 'ACTION REQUIRED')
                  : isSubmissionAuthorized ? 'SUBMISSION AUTHORIZED'
                  : isSubmissionRunning ? 'SUBMITTING...'
                  : isUnverified ? 'EXTERNAL UNVERIFIED'
                  : detail.status}
              </span>
            )}
          </div>
          <p className="text-[11px] sm:text-xs text-slate-400">
            Inspect tailored resume, cover letter, and verified answers before authorizing submission.
          </p>
        </div>

        {/* Application Dropdown & Actions */}
        <div className="flex items-center space-x-2 w-full md:w-auto">
          <select
            value={selectedAppId}
            onChange={(e) => setSelectedAppId(e.target.value)}
            disabled={applications.length === 0}
            className="flex-1 md:flex-initial px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500 md:max-w-xs disabled:opacity-50"
          >
            {applications.length === 0 ? (
              <option value="">No applications prepared</option>
            ) : (
              applications.map((app) => {
                const identifier = app.job_id_str || app.job_id || app.application_id || 'app';
                const displayId = identifier.length > 32 ? `${identifier.slice(0, 29)}...` : identifier;
                return (
                  <option 
                    key={app.application_id || app.job_id_str || app.job_id} 
                    value={app.application_id || app.job_id_str || app.job_id}
                    title={`${app.company} — ${app.role} (${identifier})`}
                  >
                    {app.company} — {app.role} ({displayId})
                  </option>
                );
              })
            )}
          </select>

          <button
            onClick={handlePrepareAgain}
            disabled={applications.length === 0 || isSubmitted}
            title="Reprepare application materials"
            className="px-3 py-2 text-xs font-semibold bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded-lg transition-colors flex items-center space-x-1.5 shrink-0 disabled:opacity-40"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Reprepare</span>
          </button>
        </div>
      </div>

      {listLoading || (selectedAppId && loading) ? (
        <div className="flex items-center justify-center min-h-[350px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : applications.length === 0 ? (
        <div className="glass-panel p-8 sm:p-12 rounded-xl text-center space-y-4 max-w-xl mx-auto border border-slate-800 my-6">
          <div className="w-12 h-12 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <div className="space-y-1.5">
            <h3 className="text-base font-bold text-white">No Applications Prepared for Review Yet</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
              When you find a high-fit role in your <b>Priority Queue</b>, click <b>"Prepare Application"</b> to tailor your resume, generate answers grounded in verified evidence, and review everything here.
            </p>
          </div>
          <div className="pt-2">
            <button
              onClick={() => onNavigateTab('queue')}
              className="px-5 py-2.5 text-xs font-semibold bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white rounded-lg transition-colors shadow-sm inline-flex items-center space-x-2"
            >
              <span>Explore Priority Queue</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : !detail ? (
        <div className="glass-panel p-8 rounded-xl text-center text-slate-400 my-6">
          <p>Please select an application to review.</p>
        </div>
      ) : (
        <div className="space-y-4 sm:space-y-6">
          
          {/* Target Opportunity Header Card */}
          <div className="glass-card p-4 sm:p-5 rounded-xl border border-slate-800 space-y-3 sm:space-y-4">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                  <span className="text-lg sm:text-xl font-bold text-white">{detail.company}</span>
                  <span className="text-slate-600 hidden sm:inline">•</span>
                  <span className="text-sm sm:text-base text-slate-300 font-medium">{detail.role}</span>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                  <span>Source: <b className="text-slate-300">{formatSource(detail.source)}</b></span>
                  <span className="hidden sm:inline">•</span>
                  <span>Strategy: <code className="font-mono text-emerald-400 uppercase font-semibold">{detail.selected_strategy}</code></span>
                  {detail.match_score && (
                    <>
                      <span className="hidden sm:inline">•</span>
                      <span>Fit Score: <b className="text-white">{Math.round(detail.match_score)}%</b></span>
                    </>
                  )}
                </div>
              </div>

              {/* Dynamic State-Driven Action Controls */}
              <div className="w-full md:w-auto pt-1 md:pt-0 flex flex-wrap items-center gap-2">
                {isBlockerActive ? (
                  detail.can_resume ? (
                    <button
                      onClick={handleResume}
                      disabled={resuming}
                      className="w-full md:w-auto px-5 py-2.5 text-xs sm:text-sm font-bold bg-amber-500 hover:bg-amber-400 active:bg-amber-600 text-slate-950 rounded-lg shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center space-x-2"
                    >
                      {resuming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                      <span>Resume Automation</span>
                    </button>
                  ) : (
                    <a
                      href={detail.canonical_job_url || detail.browser_review?.target_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full md:w-auto px-4 py-2.5 text-xs sm:text-sm font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center space-x-2"
                    >
                      <ExternalLink className="w-4 h-4" />
                      <span>Open Employer Portal</span>
                    </a>
                  )
                ) : isSubmissionAuthorized ? (
                  <div className="w-full md:w-auto px-4 py-2.5 text-xs font-semibold bg-blue-900/30 text-blue-300 border border-blue-500/40 rounded-lg flex items-center justify-center space-x-2">
                    <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                    <span>Submission authorized — waiting for browser worker</span>
                  </div>
                ) : isSubmissionRunning ? (
                  <div className="w-full md:w-auto px-4 py-2.5 text-xs font-semibold bg-blue-900/40 text-blue-200 border border-blue-400/50 rounded-lg flex items-center justify-center space-x-2">
                    <Loader2 className="w-4 h-4 animate-spin text-blue-300" />
                    <span>Submitting application...</span>
                  </div>
                ) : isReadyToConfirm ? (
                  <button
                    onClick={() => setShowSubmissionModal(true)}
                    className="w-full md:w-auto px-5 py-2.5 text-xs sm:text-sm font-bold bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white rounded-lg shadow-lg shadow-rose-600/20 transition-all flex items-center justify-center space-x-2"
                  >
                    <Send className="w-4 h-4" />
                    <span>Authorize Submission</span>
                  </button>
                ) : isSubmitted && !isUnverified ? (
                  <div className="w-full md:w-auto px-4 py-2.5 text-xs font-semibold bg-emerald-950/40 text-emerald-300 border border-emerald-500/40 rounded-lg flex items-center justify-center space-x-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <div className="text-left">
                      <div className="font-bold text-emerald-300">✓ Application submitted</div>
                      <div className="text-[10px] text-emerald-400 font-normal">Employer confirmation verified</div>
                    </div>
                  </div>
                ) : isUnverified ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="px-3.5 py-2 text-xs font-semibold bg-amber-950/40 text-amber-300 border border-amber-500/40 rounded-lg flex items-center space-x-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      <span>Submission unverified</span>
                    </div>
                    <button
                      onClick={() => setShowRetryModal(true)}
                      className="px-4 py-2 text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white rounded-lg shadow-sm transition-colors flex items-center space-x-1.5 cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Review & Retry Submission</span>
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={handlePrepareAgain}
                    disabled={loading}
                    className="w-full md:w-auto px-5 py-2.5 text-xs sm:text-sm font-bold bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white rounded-lg shadow-lg shadow-blue-600/20 transition-all flex items-center justify-center space-x-2"
                  >
                    <Sparkles className="w-4 h-4" />
                    <span>Prepare Application Materials</span>
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Prominent Blocker / Human Action Required Card (Option B: Safe Manual Takeover) */}
          {isBlockerActive && (
            <div className="glass-panel p-4 sm:p-5 rounded-xl border-2 border-amber-500/60 bg-amber-950/25 space-y-3 animate-in fade-in">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start space-x-3">
                  <div className="p-2 sm:p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/40 shrink-0 mt-0.5">
                    <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 animate-pulse" />
                  </div>
                  <div className="space-y-1">
                    <h4 className="text-sm sm:text-base font-bold text-amber-200 uppercase tracking-wide">
                      {detail.blocker_type === 'CAPTCHA' ? 'CAPTCHA Verification Required' :
                       detail.blocker_type === 'LOGIN' ? 'Authentication Login Required' :
                       detail.blocker_type === 'MFA' ? 'MFA / OTP Challenge' :
                       detail.blocker_type === 'USER_INPUT_REQUIRED' ? 'Candidate Input Required' :
                       'Manual Action Required'}
                    </h4>
                    <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-medium">
                      {detail.blocker_instruction || detail.browser_review?.pause_reason || (
                        detail.can_resume
                          ? 'Please provide the missing information in the Needs Input tab, then click Resume.'
                          : 'The automated browser cannot safely continue because human interaction is required. Complete this application manually in the employer portal. The automation will not submit or retry automatically.'
                      )}
                    </p>
                  </div>
                </div>

                {detail.can_resume ? (
                  <button
                    onClick={handleResume}
                    disabled={resuming}
                    className="px-5 py-2.5 text-xs sm:text-sm font-bold bg-amber-500 hover:bg-amber-400 active:bg-amber-600 text-slate-950 rounded-lg shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center space-x-2 shrink-0 disabled:opacity-50"
                  >
                    {resuming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    <span>Resume Automation</span>
                  </button>
                ) : (
                  <a
                    href={detail.canonical_job_url || detail.browser_review?.target_url || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-5 py-2.5 text-xs sm:text-sm font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center space-x-2 shrink-0"
                  >
                    <ExternalLink className="w-4 h-4" />
                    <span>Open Employer Portal</span>
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Historical Record / External Unverified Banner */}
          {isUnverified && (
            <div className="glass-panel p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2 text-amber-300 font-bold">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>INTERNAL RECORD (EXTERNAL SUBMISSION UNVERIFIED)</span>
                </div>
                <button
                  onClick={() => setShowRetryModal(true)}
                  className="px-3 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded text-[11px] font-semibold transition-colors cursor-pointer"
                >
                  Review & Retry
                </button>
              </div>
              <p className="text-slate-300 leading-relaxed pl-6">
                Submission outcome could not be verified from external employer confirmation. Retrying could create a duplicate application if the employer already received it. Automated retry is strictly blocked without explicit duplicate risk acknowledgement.
              </p>
            </div>
          )}

          {/* Mobile-Swipeable Sub-Navigation Tabs */}
          <div className="flex items-center space-x-1.5 overflow-x-auto pb-2 border-b border-slate-800 text-xs font-medium scrollbar-none no-scrollbar -mx-2 px-2">
            <button
              onClick={() => setActiveSubTab('resume')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 shrink-0 ${
                activeSubTab === 'resume' ? 'bg-blue-600/25 text-blue-300 border border-blue-500/40 font-semibold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Resume & Cover Letter</span>
            </button>

            <button
              onClick={() => setActiveSubTab('answers')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 shrink-0 ${
                activeSubTab === 'answers' ? 'bg-blue-600/25 text-blue-300 border border-blue-500/40 font-semibold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Prepared Q&A ({detail.prepared_answers.length})</span>
            </button>

            <button
              onClick={() => setActiveSubTab('human_input')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 shrink-0 ${
                activeSubTab === 'human_input' ? 'bg-purple-600/25 text-purple-300 border border-purple-500/40 font-semibold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <HelpCircle className="w-4 h-4" />
              <span>Needs Input ({detail.user_inputs_required.length})</span>
            </button>

            <button
              onClick={() => setActiveSubTab('browser')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 shrink-0 ${
                activeSubTab === 'browser' ? 'bg-amber-600/25 text-amber-300 border border-amber-500/40 font-semibold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Eye className="w-4 h-4" />
              <span>Browser Review</span>
            </button>

            <button
              onClick={() => setActiveSubTab('timeline')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 shrink-0 ${
                activeSubTab === 'timeline' ? 'bg-slate-800 text-slate-200 font-semibold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Clock className="w-4 h-4" />
              <span>Timeline ({detail.timeline.length})</span>
            </button>
          </div>

          {/* Sub-Tab 1: Resume & Cover Letter */}
          {activeSubTab === 'resume' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
              
              {/* Resume Panel with PDF / LaTeX toggle */}
              <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800">
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-blue-400" />
                    <span>Tailored Resume</span>
                  </h3>
                  
                  {/* View Switcher & Action Buttons */}
                  <div className="flex items-center space-x-2">
                    <div className="flex items-center bg-slate-900 border border-slate-800 p-0.5 rounded-lg text-xs">
                      <button
                        onClick={() => setResumeViewMode('pdf')}
                        className={`px-2.5 py-1 rounded-md font-medium transition-all flex items-center space-x-1.5 ${
                          resumeViewMode === 'pdf' 
                            ? 'bg-blue-600 text-white shadow-sm font-semibold' 
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>PDF</span>
                      </button>
                      
                      <button
                        onClick={() => setResumeViewMode('latex')}
                        className={`px-2.5 py-1 rounded-md font-medium transition-all flex items-center space-x-1.5 ${
                          resumeViewMode === 'latex' 
                            ? 'bg-blue-600 text-white shadow-sm font-semibold' 
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <FileCode className="w-3.5 h-3.5" />
                        <span>LaTeX</span>
                      </button>
                    </div>

                    {resumeViewMode === 'latex' ? (
                      <button
                        onClick={handleCopyTex}
                        className="p-1.5 rounded-lg text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 text-xs flex items-center space-x-1 border border-slate-700 transition-colors"
                        title="Copy LaTeX Source"
                      >
                        {copiedTex ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedTex ? 'Copied' : 'Copy'}</span>
                      </button>
                    ) : (
                      <button
                        onClick={handleOpenPdf}
                        className="p-1.5 rounded-lg text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 text-xs flex items-center space-x-1 border border-slate-700 transition-colors cursor-pointer"
                        title="Open PDF in new tab"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>Open</span>
                      </button>
                    )}
                  </div>
                </div>

                {resumeViewMode === 'pdf' ? (
                  <div className="space-y-2">
                    {pdfLoading ? (
                      <div className="w-full h-[400px] sm:h-[500px] rounded-lg border border-slate-800 bg-slate-950 flex flex-col items-center justify-center space-y-2 text-slate-400 text-xs">
                        <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
                        <span>Loading compiled PDF...</span>
                      </div>
                    ) : pdfBlobUrl ? (
                      <iframe
                        src={pdfBlobUrl}
                        className="w-full h-[400px] sm:h-[500px] rounded-lg border border-slate-800 bg-slate-950"
                        title="Compiled Resume PDF"
                      />
                    ) : (
                      <div className="w-full h-[400px] sm:h-[500px] rounded-lg border border-slate-800 bg-slate-950 flex items-center justify-center text-slate-500 text-xs">
                        Failed to load resume PDF preview.
                      </div>
                    )}
                    <div className="flex items-center justify-between text-[11px] text-slate-400 px-1 pt-1">
                      <span>Compiled via Tectonic Engine</span>
                      <button
                        onClick={handleDownloadPdf}
                        disabled={downloadingPdf}
                        className="text-blue-400 hover:underline flex items-center space-x-1 font-semibold cursor-pointer disabled:opacity-50"
                      >
                        {downloadingPdf ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                        <span>{downloadingPdf ? 'Downloading...' : 'Download PDF'}</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <pre className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-300 max-h-[450px] sm:max-h-[500px] overflow-y-auto overflow-x-auto leading-relaxed whitespace-pre font-mono select-text">
                      {detail.resume_tex_content || '% Tailored LaTeX generated for this opportunity\n\\begin{document}\n...'}
                    </pre>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
                      <span>Full LaTeX source preserved • {detail.resume_tex_content ? `${detail.resume_tex_content.length} characters` : 'No source'}</span>
                      <button
                        onClick={handleCopyTex}
                        className="text-blue-400 hover:underline flex items-center space-x-1 font-semibold cursor-pointer"
                      >
                        {copiedTex ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedTex ? 'Copied' : 'Copy LaTeX'}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Cover Letter Panel */}
              <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    <span>Tailored Cover Letter</span>
                  </h3>
                  <button
                    onClick={handleCopyCover}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs flex items-center space-x-1 border border-slate-800"
                  >
                    {copiedCover ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedCover ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>

                {detail.cover_letter_subject && (
                  <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-semibold text-slate-200">
                    Subject: {detail.cover_letter_subject}
                  </div>
                )}

                <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 max-h-[440px] overflow-y-auto leading-relaxed whitespace-pre-wrap font-sans">
                  {detail.cover_letter_text || 'No tailored cover letter generated for this opportunity.'}
                </div>
              </div>

            </div>
          )}

          {/* Sub-Tab 2: Prepared Answers */}
          {activeSubTab === 'answers' && (
            <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-blue-400" />
                <span>Evidence-Grounded Application Answers</span>
              </h3>

              <div className="space-y-3">
                {detail.prepared_answers.length === 0 ? (
                  <div className="text-xs text-slate-500 py-6 text-center">No application questions detected or answered.</div>
                ) : (
                  detail.prepared_answers.map((ans, idx) => (
                    <div 
                      key={idx}
                      className="p-3.5 sm:p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-1.5">
                        <span className="font-semibold text-slate-200 text-sm">{ans.question_text}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 uppercase">
                          {ans.field_category}
                        </span>
                      </div>

                      <div className="p-3 bg-slate-950 rounded-lg border border-slate-800/80 text-slate-100 font-sans leading-relaxed">
                        {ans.answer_text}
                      </div>

                      {ans.source_evidence.length > 0 && (
                        <div className="text-[11px] text-slate-400 font-mono">
                          Evidence Citation: <span className="text-emerald-400">{ans.source_evidence.join(', ')}</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Sub-Tab 3: Needs Human Input */}
          {activeSubTab === 'human_input' && (
            <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <HelpCircle className="w-4 h-4 text-purple-400" />
                    <span>Sensitive Questions Requiring Explicit Human Input</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Answers provided here are stored directly in the application session without mutating candidate truth YAML files.
                  </p>
                </div>

                <button
                  onClick={handleSaveInputs}
                  disabled={savingInputs}
                  className="w-full sm:w-auto px-4 py-2.5 text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors flex items-center justify-center space-x-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{savingInputs ? 'Saving...' : 'Save Answers'}</span>
                </button>
              </div>

              {inputSavedMsg && (
                <div className="p-3 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Application answers successfully saved and bound to this opportunity.</span>
                </div>
              )}

              <div className="space-y-3 sm:space-y-4">
                {detail.user_inputs_required.length === 0 ? (
                  <div className="text-xs text-slate-500 py-8 text-center bg-slate-900/30 rounded-xl border border-slate-800">
                    No unresolved or sensitive input fields required for this role.
                  </div>
                ) : (
                  detail.user_inputs_required.map((req) => (
                    <div 
                      key={req.question_id}
                      className="p-3.5 sm:p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-1.5">
                        <label className="font-semibold text-slate-200 text-sm">
                          {req.question_text}
                        </label>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">
                          {req.reason_required}
                        </span>
                      </div>

                      <input
                        type="text"
                        placeholder="Enter value (e.g. Authorized to work without sponsorship / 30 Days Notice)"
                        value={humanAnswers[req.question_id] || ''}
                        onChange={(e) => setHumanAnswers({ ...humanAnswers, [req.question_id]: e.target.value })}
                        className="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-purple-500"
                      />
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Sub-Tab 4: Browser Review */}
          {activeSubTab === 'browser' && (
            <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
              
              {/* Unmistakable READY_FOR_REVIEW Alert Banner */}
              <div className="p-4 rounded-xl bg-amber-950/25 border-2 border-amber-500/50 text-amber-200 space-y-1.5">
                <div className="flex items-center space-x-2 text-amber-400 font-bold text-sm tracking-wide uppercase">
                  <ShieldAlert className="w-5 h-5 flex-shrink-0" />
                  <span>Ready For Your Review — The application has NOT been sent</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  The browser worker has inspected the form and mapped verified candidate evidence. Review all fields below. External submission requires your explicit confirmation keyword.
                </p>
              </div>

              {detail.browser_review ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                      <span className="text-slate-400">Task Status:</span>
                      <div className="text-sm font-bold text-white mt-0.5">{detail.browser_review.status}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                      <span className="text-slate-400">Form Fields Filled:</span>
                      <div className="text-sm font-bold text-emerald-400 mt-0.5">
                        {detail.browser_review.fields_filled_count} / {detail.browser_review.fields_detected_count}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                      <span className="text-slate-400">Confirmation Token:</span>
                      <div className="text-sm font-bold text-blue-400 mt-0.5 font-mono">
                        {detail.browser_review.has_confirmation_token ? 'Active & Valid' : 'Not generated'}
                      </div>
                    </div>
                  </div>

                  {detail.browser_review.has_screenshot && detail.browser_review.screenshot_artifact_id && (
                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-slate-300">Browser Pre-Submission Screenshot:</span>
                      <div className="rounded-xl overflow-hidden border border-slate-800 max-h-96 bg-slate-950 flex items-center justify-center min-h-[160px]">
                        {screenshotBlobUrl ? (
                          <img 
                            src={screenshotBlobUrl}
                            alt="Pre-submission screenshot"
                            className="w-full object-cover"
                          />
                        ) : (
                          <div className="text-slate-500 text-xs flex items-center space-x-2">
                            <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                            <span>Loading screenshot...</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-xs text-slate-500 py-8 text-center bg-slate-900/30 rounded-xl border border-slate-800">
                  No active browser review package found for this application.
                </div>
              )}
            </div>
          )}

          {/* Sub-Tab 5: Timeline */}
          {activeSubTab === 'timeline' && (
            <div className="glass-panel p-4 sm:p-5 rounded-xl space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                <Clock className="w-4 h-4 text-blue-400" />
                <span>Append-Only Lifecycle Timeline</span>
              </h3>

              <div className="space-y-2.5">
                {detail.timeline.length === 0 ? (
                  <div className="text-xs text-slate-500 py-6 text-center">No lifecycle events recorded.</div>
                ) : (
                  detail.timeline.map((evt) => (
                    <div 
                      key={evt.event_id}
                      className="flex items-start space-x-3 p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-xs"
                    >
                      <div className="w-2 h-2 rounded-full bg-blue-400 mt-1.5 shrink-0"></div>
                      <div className="flex-1 space-y-0.5 min-w-0">
                        <div className="flex flex-wrap items-center justify-between gap-1">
                          <span className="font-semibold text-slate-200">{evt.event_type}</span>
                          <span className="text-[10px] font-mono text-slate-500">
                            {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : ''}
                          </span>
                        </div>
                        <div className="text-slate-400 truncate">
                          Source: <span className="font-mono text-slate-300">{formatSource(evt.source)}</span>
                          {evt.notes && <span className="ml-2 text-slate-400">• {evt.notes}</span>}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

        </div>
      )}

      {/* Strict Submission Modal */}
      {showSubmissionModal && detail && (
        <SubmissionModal
          applicationId={detail.application_id}
          jobId={detail.job_id}
          company={detail.company}
          role={detail.role}
          source={detail.source}
          targetUrl={detail.canonical_job_url}
          strategy={detail.selected_strategy}
          taskId={detail.browser_review?.task_id || ''}
          confirmationToken={detail.browser_review?.confirmation_token || ''}
          onClose={() => setShowSubmissionModal(false)}
          onSuccess={() => {
            api.getApplicationDetail(detail.application_id).then(setDetail);
          }}
        />
      )}

      {/* Review & Retry Submission Modal */}
      {showRetryModal && detail && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-amber-500/40 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/40">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Review & Retry Submission</h3>
                  <p className="text-xs text-slate-400">{detail.company} — {detail.role}</p>
                </div>
              </div>
              <button
                onClick={() => setShowRetryModal(false)}
                className="text-slate-400 hover:text-white text-xs p-1"
              >
                ✕
              </button>
            </div>

            {detail.application_id === 'app-usr-2a43a63d' || detail.is_external_unverified && detail.application_id.startsWith('app-usr-') ? (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs space-y-2 leading-relaxed">
                  <p className="font-semibold text-amber-300">Historical Internal Record Safeguard</p>
                  <p>
                    This application was created by an older internal system record where external confirmation was unverified.
                  </p>
                  <p>
                    Automatic retry for this historical record is strictly prevented to protect against submitting a duplicate application to the employer.
                  </p>
                  <p className="text-slate-300">
                    Please inspect your application status directly in the employer's career portal.
                  </p>
                </div>
                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => setShowRetryModal(false)}
                    className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs space-y-2 leading-relaxed">
                  <p className="font-bold text-amber-300">Warning: Risk of Duplicate Application</p>
                  <p>
                    Submission outcome could not be verified. The employer may already have received this application. Retrying could create a duplicate application.
                  </p>
                  <p>
                    Initiating retry will reset the submission cycle, clear stale confirmation tokens, and require you to review and authorize fresh submission.
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">User Notes (Optional):</label>
                  <input
                    type="text"
                    placeholder="e.g. Verified portal manually, no prior submission found."
                    value={retryNotes}
                    onChange={(e) => setRetryNotes(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <label className="flex items-start space-x-2.5 p-3 rounded-xl bg-slate-950/80 border border-slate-800 cursor-pointer text-xs">
                  <input
                    type="checkbox"
                    checked={retryAcknowledged}
                    onChange={(e) => setRetryAcknowledged(e.target.checked)}
                    className="mt-0.5 rounded border-slate-700 text-amber-500 focus:ring-amber-500"
                  />
                  <span className="text-slate-300 leading-snug">
                    I understand that retrying an unverified submission may result in a duplicate application and explicitly request a new review cycle.
                  </span>
                </label>

                <div className="flex items-center justify-end space-x-3 pt-2">
                  <button
                    onClick={() => setShowRetryModal(false)}
                    className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleRetrySubmit}
                    disabled={!retryAcknowledged || retrying}
                    className="px-5 py-2 text-xs font-bold bg-amber-600 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-all shadow-md flex items-center space-x-1.5"
                  >
                    {retrying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    <span>Proceed with Retry Review</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
};
