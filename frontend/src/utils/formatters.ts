/**
 * Utility formatters for UI presentation.
 */

export function formatSource(source?: string | null): string {
  if (!source) return 'Direct Ingestion';
  const lower = source.toLowerCase().trim();
  switch (lower) {
    case 'text_input':
      return 'Direct Input';
    case 'manual':
      return 'Manual Entry';
    case 'feed':
      return 'RSS / Feed';
    case 'crawler':
      return 'Web Discovery';
    case 'copilot':
      return 'Job Copilot';
    case 'greenhouse':
      return 'Greenhouse';
    case 'lever':
      return 'Lever';
    case 'workday':
      return 'Workday';
    case 'ashby':
      return 'Ashby';
    case 'user_submitted_url':
    case 'user_submitted':
      return 'Added by you';
    default:
      return source
        .replace(/[_-]/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

export function formatStatus(status?: string | null): string {
  if (!status) return 'DISCOVERED';
  return status.replace(/_/g, ' ').toUpperCase();
}
