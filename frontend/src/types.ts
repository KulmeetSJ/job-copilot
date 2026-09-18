export type PriorityBand = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'IGNORE';
export type QueueStatus = 'NEW' | 'REVIEW' | 'APPROVED' | 'PREPARING' | 'READY_FOR_REVIEW' | 'WAITING_FOR_USER' | 'SUBMITTED' | 'TRACKING' | 'SKIPPED' | 'ARCHIVED';
export type ApplicationMode = 'MANUAL' | 'ASSISTED' | 'AUTO_APPLY';
export type MatchClassification = 

  | 'MATCH_CONFIRMED'
  | 'MATCH_PROJECT_ONLY'
  | 'MATCH_EXPOSURE_ONLY'
  | 'MATCH_POSITIONING_ONLY'
  | 'PARTIAL_MATCH'
  | 'NO_EVIDENCE'
  | 'CONFLICT';

export interface PipelineCounts {
  discovered: number;
  recommended: number;
  prepared: number;
  ready_for_review: number;
  needs_user_input: number;
  awaiting_confirmation: number;
  manual_action_required: number;
  submission_unverified: number;
  submitted: number;
  recruiter_response: number;
  interview: number;
  offer: number;
  rejected: number;
  withdrawn: number;
}

export interface QueueCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  total_active: number;
}

export interface DashboardOverviewResponse {
  queue_counts: QueueCounts;
  pipeline_counts: PipelineCounts;
  recent_submissions_count: number;
  active_sources_count: number;
  healthy_sources_count: number;
  authenticated_sessions_count: number;
  recent_activity: Array<{
    event_id: string;
    application_id: string;
    job_id: string;
    event_type: string;
    source: string;
    notes?: string;
    timestamp?: string;
  }>;
  featured_openings?: DashboardQueueItem[];
  timestamp: string;
}

export interface DashboardQueueItem {
  job_id: string;
  company: string;
  title: string;
  location?: string;
  remote_status?: string;
  source: string;
  canonical_url?: string;
  match_score?: number;
  recommendation?: string;
  priority_band: PriorityBand;
  priority_score: number;
  queue_status: QueueStatus;
  freshness_days: number;
  key_matched_skills: string[];
  major_gaps: string[];
  risk_flags: string[];
  primary_reason?: string;
  selected_strategy?: string;
  mode?: ApplicationMode;
  tracking_application_id?: string;

  application_status?: string;
  discovered_at: string;
}

export interface DashboardQueueResponse {
  items: DashboardQueueItem[];
  total_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
}

export interface MatchDimensionScore {
  dimension_name: string;
  score: number;
  weight: number;
  description: string;
}

export interface RequirementMatchDetail {
  requirement_name: string;
  normalized_name: string;
  category: string;
  importance: string;
  is_must_have: boolean;
  classification: MatchClassification;
  confidence: number;
  evidence_ids: string[];
  evidence_text?: string;
  reason: string;
}

export interface ExplanationSection {
  facts: string[];
  inferences: string[];
  recommendations: string[];
}

export interface JobDetailResponse {
  job_id: string;
  title: string;
  company: string;
  location?: string;
  source: string;
  url?: string;
  remote_status?: string;
  employment_type?: string;
  discovered_at: string;
  lifecycle_status: string;
  description: string;
  requirements: string[];
  technologies: string[];
  salary_min?: number;
  salary_max?: number;
  currency: string;
  match_score: number;
  priority_score: number;
  priority_band: string;
  recommendation: string;
  dimension_scores: MatchDimensionScore[];
  requirement_matches: RequirementMatchDetail[];
  strengths: string[];
  partial_matches: string[];
  gaps: string[];
  risks: string[];
  explanation: ExplanationSection;
  recommended_strategy: string;
  strategy_reasoning: string;
  alternative_strategies: string[];
}

export interface PreparedAnswerItem {
  question_text: string;
  field_name?: string;
  field_category: string;
  answer_text: string;
  confidence: number;
  source_evidence: string[];
  requires_user_input: boolean;
  validation_status: string;
}

export interface UserInputRequiredItem {
  question_id: string;
  question_text: string;
  field_type: string;
  current_value?: any;
  reason_required: string;
  options?: string[];
  is_sensitive: boolean;
}

export interface ArtifactSummaryItem {
  artifact_id: string;
  artifact_type: string;
  original_filename?: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: string;
  created_at: string;
  download_url?: string;
}

export interface BrowserMappedFieldItem {
  field_id: string;
  label: string;
  name?: string;
  element_type?: string;
  action: string;
  value?: string;
  status: string;
  source?: string;
  reason?: string;
}

export interface BrowserReviewSummary {
  task_id?: string;
  source: string;
  target_url?: string;
  status: string;
  fields_detected_count: number;
  fields_filled_count: number;
  fields_requiring_input_count: number;
  has_screenshot: boolean;
  screenshot_artifact_id?: string;
  has_confirmation_token: boolean;
  confirmation_token?: string;
  is_ready_for_review: boolean;
  pause_reason?: string;
  failure_reason?: string;
  warnings: string[];
  blocker_type?: string;
  blocker_instruction?: string;
  can_resume?: boolean;
  is_external_unverified?: boolean;
  mapped_fields?: BrowserMappedFieldItem[];
}

export interface ApplicationTimelineEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  source: string;
  notes?: string;
  metadata: Record<string, any>;
}

export interface ApplicationDetailResponse {
  application_id: string;
  job_id: string;
  company: string;
  role: string;
  source: string;
  canonical_job_url?: string;
  status: string;
  match_score?: number;
  recommendation?: string;
  selected_strategy: string;
  mode?: ApplicationMode;
  resume_pdf_path?: string;

  resume_tex_content?: string;
  cover_letter_text?: string;
  cover_letter_subject?: string;
  cover_letter_valid: boolean;
  prepared_answers: PreparedAnswerItem[];
  user_inputs_required: UserInputRequiredItem[];
  artifacts: ArtifactSummaryItem[];
  browser_review?: BrowserReviewSummary;
  timeline: ApplicationTimelineEvent[];
  user_notes: string[];
  discovered_at?: string;
  prepared_at?: string;
  submitted_at?: string;
  blocker_type?: string;
  blocker_instruction?: string;
  can_resume?: boolean;
  is_external_unverified?: boolean;
}

export interface SourceMonitoringItem {
  source_name: string;
  display_name: string;
  enabled: boolean;
  discovery_mode: string;
  health_status: string;
  last_run_at?: string;
  last_error?: string;
  requires_login: boolean;
  has_active_session: boolean;
  session_status?: string;
}

export interface SessionMetadataItem {
  id: number;
  session_id: string;
  source: string;
  status: string;
  has_stored_state: boolean;
  created_at: string;
  last_verified_at?: string;
  expires_at?: string;
  metadata?: Record<string, any>;
}

export interface SubmissionConfirmResponse {
  success: boolean;
  application_id?: string;
  task_id: string;
  status: string;
  submission_reference?: string;
  submitted_at?: string;
  message: string;
}

export interface RetrySubmissionPayload {
  acknowledge_duplicate_risk: boolean;
  user_notes?: string;
}

export interface AnalyzeOpportunityRequest {
  url: string;
}

export interface AnalyzeOpportunityResponse {
  job_id: string;
  application_id?: string;
  company: string;
  title: string;
  location?: string;
  canonical_url: string;
  source: string;
  match_score: number;
  recommendation: string;
  priority_band: string;
  priority_score: number;
  selected_strategy?: string;
  strengths: string[];
  gaps: string[];
  risks: string[];
  is_duplicate: boolean;
  duplicate_of_id?: string;
  status: string;
  resume_download_url?: string;
  supports_browser_prep: boolean;
  has_active_session: boolean;
  needs_user_input_count: number;
  message: string;
}

export interface PairingCodeResponse {
  device_id: string;
  pairing_code: string;
  expires_at: string;
  server_url?: string;
  instructions: string;
  cli_command: string;
}

export interface PairedDeviceItem {
  device_id: string;
  device_name: string;
  status: string;
  is_active: boolean;
  last_seen_at?: string;
  capabilities: string[];
  agent_version: string;
  created_at?: string;
}

