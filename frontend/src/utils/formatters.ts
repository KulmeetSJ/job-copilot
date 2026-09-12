/**
 * Utility formatters for UI presentation.
 */

export function formatSource(source?: string | null): string {
  if (!source || source.toLowerCase() === 'unknown' || source.toLowerCase() === 'source unavailable') {
    return 'Source unavailable';
  }
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
    case 'url_fetch':
      return 'Added by you';
    default:
      return source
        .replace(/[_-]/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

export function formatStrategy(strategy?: string | null): string {
  if (!strategy || strategy.toLowerCase() === 'strategy unavailable' || strategy.toLowerCase() === 'unknown') {
    return 'Strategy unavailable';
  }
  const lower = strategy.toLowerCase().trim();
  switch (lower) {
    case 'backend_java':
      return 'Backend Java';
    case 'cloud_devops':
      return 'Cloud DevOps';
    case 'data_engineering':
      return 'Data Engineering';
    case 'full_stack':
      return 'Full Stack';
    case 'sre_devops':
      return 'SRE & DevOps';
    default:
      return strategy
        .replace(/[_-]/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

export function formatStatus(status?: string | null): string {
  if (!status) return 'DISCOVERED';
  return status.replace(/_/g, ' ').toUpperCase();
}
