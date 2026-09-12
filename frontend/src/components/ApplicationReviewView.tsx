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
  Check
} from 'lucide-react';
import { api } from '../api';
import { ApplicationDetailResponse } from '../types';
import { SubmissionModal } from './SubmissionModal';

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
  const [copiedTex, setCopiedTex] = useState(false);
  const [copiedCover, setCopiedCover] = useState(false);
  
  // Human Input form state
  const [humanAnswers, setHumanAnswers] = useState<Record<string, string>>({});
  const [savingInputs, setSavingInputs] = useState(false);
  const [inputSavedMsg, setInputSavedMsg] = useState(false);

  // Submission Modal state
  const [showSubmissionModal, setShowSubmissionModal] = useState(false);

  // Load application list
  useEffect(() => {
    api.listApplications().then((apps) => {
      setApplications(apps);
      if (!selectedAppId && apps.length > 0) {
        setSelectedAppId(apps[0].application_id || apps[0].job_id_str || apps[0].id.toString());
      }
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

  return (
    <div className="space-y-6">
      
      {/* Top Application Selector & Summary */}
      <div className="glass-panel p-5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center space-x-3">
            <h2 className="text-lg font-bold text-white tracking-tight">
              Application Review & Material Inspection
            </h2>
            {detail?.status && (
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                detail.status === 'READY_FOR_REVIEW' 
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse'
                  : detail.status === 'SUBMITTED'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
              }`}>
                {detail.status}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400">
            Inspect tailored resume, cover letter, and evidence-grounded answers before authorizing submission.
          </p>
        </div>

        {/* Application Dropdown */}
        <div className="flex items-center space-x-3 w-full md:w-auto">
          <select
            value={selectedAppId}
            onChange={(e) => setSelectedAppId(e.target.value)}
            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500 max-w-xs"
          >
            {applications.map((app) => (
              <option key={app.application_id || app.job_id_str} value={app.application_id || app.job_id_str}>
                {app.company} — {app.role} ({app.status})
              </option>
            ))}
          </select>

          <button
            onClick={handlePrepareAgain}
            className="px-3 py-2 text-xs font-semibold bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded-lg transition-colors flex items-center space-x-1.5 whitespace-nowrap"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Reprepare</span>
          </button>
        </div>
      </div>

      {loading || !detail ? (
        <div className="flex items-center justify-center min-h-[350px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="space-y-6">
          
          {/* Target Opportunity Header Card */}
          <div className="glass-card p-5 rounded-xl border border-slate-800 space-y-3">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center space-x-3">
                  <span className="text-xl font-bold text-white">{detail.company}</span>
                  <span className="text-slate-600">•</span>
                  <span className="text-base text-slate-300 font-medium">{detail.role}</span>
                </div>
                <div className="flex items-center space-x-3 text-xs text-slate-400">
                  <span className="capitalize">Source: {detail.source}</span>
                  <span>•</span>
                  <span>Strategy: <code className="font-mono text-emerald-400 uppercase font-semibold">{detail.selected_strategy}</code></span>
                  {detail.match_score && (
                    <>
                      <span>•</span>
                      <span>Fit Score: <b className="text-white">{Math.round(detail.match_score)}%</b></span>
                    </>
                  )}
                </div>
              </div>

              {/* Consequential Action Confirmation Button */}
              <div className="flex items-center space-x-3">
                <button
                  onClick={() => setShowSubmissionModal(true)}
                  className="px-5 py-2.5 text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white rounded-lg shadow-lg shadow-rose-600/20 transition-all flex items-center space-x-2"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Authorize & Submit</span>
                </button>
              </div>
            </div>
          </div>

          {/* Sub-Navigation Tabs */}
          <div className="flex items-center space-x-1 border-b border-slate-800 pb-2 text-xs font-medium">
            <button
              onClick={() => setActiveSubTab('resume')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 ${
                activeSubTab === 'resume' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Tailored Resume & Cover Letter</span>
            </button>

            <button
              onClick={() => setActiveSubTab('answers')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 ${
                activeSubTab === 'answers' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Prepared Q&A ({detail.prepared_answers.length})</span>
            </button>

            <button
              onClick={() => setActiveSubTab('human_input')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 ${
                activeSubTab === 'human_input' ? 'bg-purple-600/20 text-purple-400 border border-purple-500/30' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <HelpCircle className="w-4 h-4" />
              <span>Needs Human Input ({detail.user_inputs_required.length})</span>
            </button>

            <button
              onClick={() => setActiveSubTab('browser')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 ${
                activeSubTab === 'browser' ? 'bg-amber-600/20 text-amber-400 border border-amber-500/30' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Eye className="w-4 h-4" />
              <span>Browser Review Package</span>
            </button>

            <button
              onClick={() => setActiveSubTab('timeline')}
              className={`px-3.5 py-2 rounded-lg transition-colors flex items-center space-x-2 ${
                activeSubTab === 'timeline' ? 'bg-slate-800 text-slate-200' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Clock className="w-4 h-4" />
              <span>Timeline ({detail.timeline.length})</span>
            </button>
          </div>

          {/* Sub-Tab 1: Resume & Cover Letter */}
          {activeSubTab === 'resume' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              
              {/* LaTeX Resume Panel */}
              <div className="glass-panel p-5 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-blue-400" />
                    <span>Tailored Resume (LaTeX Source)</span>
                  </h3>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={handleCopyTex}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs flex items-center space-x-1"
                    >
                      {copiedTex ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedTex ? 'Copied' : 'Copy'}</span>
                    </button>
                    {detail.resume_pdf_path && (
                      <span className="text-xs text-slate-500 font-mono">PDF compiled</span>
                    )}
                  </div>
                </div>

                <pre className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-300 max-h-[480px] overflow-y-auto leading-relaxed whitespace-pre-wrap">
                  {detail.resume_tex_content || '% Tailored LaTeX generated for this opportunity\n\\begin{document}\n...'}
                </pre>
              </div>

              {/* Cover Letter Panel */}
              <div className="glass-panel p-5 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    <span>Tailored Cover Letter</span>
                  </h3>
                  <button
                    onClick={handleCopyCover}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs flex items-center space-x-1"
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
            <div className="glass-panel p-5 rounded-xl space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-blue-400" />
                <span>Phase 6 Evidence-Grounded Application Answers</span>
              </h3>

              <div className="space-y-3">
                {detail.prepared_answers.length === 0 ? (
                  <div className="text-xs text-slate-500 py-6 text-center">No application questions detected or answered.</div>
                ) : (
                  detail.prepared_answers.map((ans, idx) => (
                    <div 
                      key={idx}
                      className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
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

          {/* Sub-Tab 3: Needs Human Input ("Human Input") */}
          {activeSubTab === 'human_input' && (
            <div className="glass-panel p-5 rounded-xl space-y-4">
              <div className="flex items-center justify-between">
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
                  className="px-4 py-2 text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors flex items-center space-x-1.5"
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

              <div className="space-y-4">
                {detail.user_inputs_required.length === 0 ? (
                  <div className="text-xs text-slate-500 py-8 text-center bg-slate-900/30 rounded-xl border border-slate-800">
                    No unresolved or sensitive input fields required for this role.
                  </div>
                ) : (
                  detail.user_inputs_required.map((req) => (
                    <div 
                      key={req.question_id}
                      className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
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
                        className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-purple-500"
                      />
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Sub-Tab 4: Browser Review */}
          {activeSubTab === 'browser' && (
            <div className="glass-panel p-5 rounded-xl space-y-4">
              
              {/* Unmistakable READY_FOR_REVIEW Alert Banner */}
              <div className="p-4 rounded-xl bg-amber-950/25 border-2 border-amber-500/50 text-amber-200 space-y-1.5">
                <div className="flex items-center space-x-2 text-amber-400 font-bold text-sm tracking-wide uppercase">
                  <ShieldAlert className="w-5 h-5" />
                  <span>Ready For Your Review — The application has NOT been sent</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  The browser worker has inspected the form and mapped verified candidate evidence. Review all fields below. External submission requires your explicit confirmation keyword.
                </p>
              </div>

              {detail.browser_review ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
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
                      <div className="rounded-xl overflow-hidden border border-slate-800 max-h-96">
                        <img 
                          src={`/api/dashboard/artifacts/${detail.browser_review.screenshot_artifact_id}/content`}
                          alt="Pre-submission screenshot"
                          className="w-full object-cover"
                        />
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
            <div className="glass-panel p-5 rounded-xl space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                <Clock className="w-4 h-4 text-blue-400" />
                <span>Append-Only Lifecycle Timeline</span>
              </h3>

              <div className="space-y-3">
                {detail.timeline.length === 0 ? (
                  <div className="text-xs text-slate-500 py-6 text-center">No lifecycle events recorded.</div>
                ) : (
                  detail.timeline.map((evt, idx) => (
                    <div 
                      key={evt.event_id}
                      className="flex items-start space-x-3 p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-xs"
                    >
                      <div className="w-2 h-2 rounded-full bg-blue-400 mt-1.5"></div>
                      <div className="flex-1 space-y-0.5">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-200">{evt.event_type}</span>
                          <span className="text-[10px] font-mono text-slate-500">
                            {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : ''}
                          </span>
                        </div>
                        <div className="text-slate-400">
                          Source: <span className="font-mono text-slate-300">{evt.source}</span>
                          {evt.notes && <span className="ml-2">• {evt.notes}</span>}
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
          taskId={detail.browser_review?.task_id || `task-${detail.application_id}`}
          confirmationToken={detail.browser_review?.has_confirmation_token ? 'CONFIRM-TOKEN-ACTIVE' : 'CONFIRM-DEV-TOKEN'}
          onClose={() => setShowSubmissionModal(false)}
          onSuccess={() => {
            api.getApplicationDetail(detail.application_id).then(setDetail);
          }}
        />
      )}

    </div>
  );
};
