// Exact labels and colours from spec 24.4 / 26.3.
const STYLES = {
  ready: { label: 'Ready', cls: 'bg-ready-bg text-ready-fg' },
  one_course_first: { label: 'One course first', cls: 'bg-onefirst-bg text-onefirst-fg' },
  not_sure: { label: 'Not sure', cls: 'bg-notsure-bg text-notsure-fg' },
}

export default function ReadinessBadge({ state }) {
  const s = STYLES[state] || STYLES.not_sure
  return <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>
}
