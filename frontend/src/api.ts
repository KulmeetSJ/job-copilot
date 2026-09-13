import {
  AnalyzeOpportunityResponse,
  ApplicationDetailResponse,
  DashboardOverviewResponse,
  DashboardQueueResponse,
  JobDetailResponse,
  PairedDeviceItem,
  PairingCodeResponse,
  PriorityBand,
  QueueStatus,
  SessionMetadataItem,
  SourceMonitoringItem,
  SubmissionConfirmResponse,
} from './types';

const API_BASE = '/api/dashboard';

function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  const key = localStorage.getItem('copilot_api_key');
  if (key) {
    headers['X-API-Key'] = key;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.detail) {
        errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export const api = {
  // Overview
  async getOverview(): Promise<DashboardOverviewResponse> {
    const res = await fetch(`${API_BASE}/overview`, { headers: getHeaders() });
    return handleResponse<DashboardOverviewResponse>(res);
  },

  // Priority Queue
  async getQueue(params?: {
    status?: QueueStatus;
    priority?: PriorityBand;
    min_score?: number;
  }): Promise<DashboardQueueResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.priority) query.append('priority', params.priority);
    if (params?.min_score !== undefined) query.append('min_score', params.min_score.toString());

    const url = `${API_BASE}/queue${query.toString() ? `?${query.toString()}` : ''}`;
    const res = await fetch(url, { headers: getHeaders() });
    return handleResponse<DashboardQueueResponse>(res);
  },

  // Job Detail & Match Explanation
  async getJobDetail(jobId: string): Promise<JobDetailResponse> {
    const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`, { headers: getHeaders() });
    return handleResponse<JobDetailResponse>(res);
  },

  // Applications
  async listApplications(status?: string, strategy?: string): Promise<any[]> {
    const query = new URLSearchParams();
    if (status) query.append('status', status);
    if (strategy) query.append('strategy', strategy);
    const url = `${API_BASE}/applications${query.toString() ? `?${query.toString()}` : ''}`;
    const res = await fetch(url, { headers: getHeaders() });
    return handleResponse<any[]>(res);
  },

  async getApplicationDetail(applicationId: string): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}`, { headers: getHeaders() });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  // Actions
  async prepareApplication(applicationId: string, strategyOverride?: string): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}/prepare`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ strategy_override: strategyOverride }),
    });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  async skipApplication(applicationId: string, reason?: string): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}/skip`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ reason }),
    });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  async submitHumanInput(
    applicationId: string,
    answers: Array<{ question_id: string; question_text: string; answer_value: any }>
  ): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}/input`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ answers }),
    });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  async confirmSubmission(params: {
    applicationId: string;
    taskId: string;
    confirmationToken: string;
    confirmText: string;
    userNotes?: string;
  }): Promise<SubmissionConfirmResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(params.applicationId)}/confirm`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        task_id: params.taskId,
        confirmation_token: params.confirmationToken,
        confirm_text: params.confirmText,
        user_notes: params.userNotes,
      }),
    });
    return handleResponse<SubmissionConfirmResponse>(res);
  },

  async resumeApplication(applicationId: string): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}/resume`, {
      method: 'POST',
      headers: getHeaders(),
    });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  async retryApplication(applicationId: string, payload: import('./types').RetrySubmissionPayload): Promise<ApplicationDetailResponse> {
    const res = await fetch(`${API_BASE}/applications/${encodeURIComponent(applicationId)}/retry`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse<ApplicationDetailResponse>(res);
  },

  // Analytics
  async getAnalytics(fromDate?: string, toDate?: string): Promise<any> {
    const query = new URLSearchParams();
    if (fromDate) query.append('from_date', fromDate);
    if (toDate) query.append('to_date', toDate);
    const url = `${API_BASE}/analytics${query.toString() ? `?${query.toString()}` : ''}`;
    const res = await fetch(url, { headers: getHeaders() });
    return handleResponse<any>(res);
  },

  // Sources & Sessions
  async getSources(): Promise<SourceMonitoringItem[]> {
    const res = await fetch(`${API_BASE}/sources`, { headers: getHeaders() });
    return handleResponse<SourceMonitoringItem[]>(res);
  },

  async getSessions(): Promise<SessionMetadataItem[]> {
    const res = await fetch(`${API_BASE}/sessions`, { headers: getHeaders() });
    return handleResponse<SessionMetadataItem[]>(res);
  },

  // Activity Log
  async getActivity(limit: number = 50): Promise<any[]> {
    const res = await fetch(`${API_BASE}/activity?limit=${limit}`, { headers: getHeaders() });
    return handleResponse<any[]>(res);
  },

  // User-Submitted Opportunities
  async analyzeOpportunity(url: string): Promise<AnalyzeOpportunityResponse> {
    const res = await fetch(`${API_BASE}/opportunities/analyze`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ url }),
    });
    return handleResponse<AnalyzeOpportunityResponse>(res);
  },

  // Authenticated File Download & Binary Content
  async downloadFile(url: string, defaultFilename?: string): Promise<void> {
    const res = await fetch(url, { headers: getHeaders() });
    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data.detail) {
          errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
      } catch {
        // ignore
      }
      throw new Error(errorMsg);
    }

    let filename = defaultFilename || 'download';
    const disposition = res.headers.get('Content-Disposition');
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename="?([^";]+)"?/);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blob = await res.blob();
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(objectUrl);
  },

  async fetchBlobUrl(url: string): Promise<string> {
    const res = await fetch(url, { headers: getHeaders() });
    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data.detail) {
          errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
      } catch {
        // ignore
      }
      throw new Error(errorMsg);
    }
    const blob = await res.blob();
    return window.URL.createObjectURL(blob);
  },

  // Paired Devices (Local Browser Agent)
  async generatePairingCode(deviceName: string = 'Local Browser Agent'): Promise<PairingCodeResponse> {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const query = new URLSearchParams({
      device_name: deviceName,
      ...(origin ? { server_url: origin } : {}),
    });
    const res = await fetch(`${API_BASE}/devices/pair-code?${query.toString()}`, {
      method: 'POST',
      headers: getHeaders(),
    });
    return handleResponse<PairingCodeResponse>(res);
  },

  async listDevices(): Promise<PairedDeviceItem[]> {
    const res = await fetch(`${API_BASE}/devices`, { headers: getHeaders() });
    return handleResponse<PairedDeviceItem[]>(res);
  },

  async revokeDevice(deviceId: string): Promise<{ success: boolean; device_id: string; message: string }> {
    const res = await fetch(`${API_BASE}/devices/${deviceId}/revoke`, {
      method: 'POST',
      headers: getHeaders(),
    });
    return handleResponse<{ success: boolean; device_id: string; message: string }>(res);
  },
};


