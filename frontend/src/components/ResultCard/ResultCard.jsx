// S20 card (spec 26.3). Never shows score or any value from features.
import { useState } from 'react'
import ReadinessBadge from './ReadinessBadge.jsx'
import ExplanationPanel from '../ExplanationPanel/ExplanationPanel.jsx'
import SimText from '../SimText.jsx'

export default function ResultCard({ result, rank, saved, onFeedback, log }) {
  const [open, setOpen] = useState(false)
  const toggle = () => {
    log(open ? 'collapse' : 'expand', { courseCode: result.code, payload: { rank } })
    setOpen(!open)
  }
  return (
    <article data-testid="result-card" className="rounded border border-line p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold">{result.code} {result.title}</h3>
        <ReadinessBadge state={result.readiness.state} />
      </div>
      <p className="mt-1 text-sm text-muted"><SimText text={result.explanation.short} /></p>
      <div className="mt-2 flex gap-4 text-sm">
        <button type="button" className="text-accent underline" aria-expanded={open} onClick={toggle}>Why this?</button>
        <button type="button" onClick={() => onFeedback(result, rank, saved ? 'unsave' : 'save')}
          className={saved ? 'font-medium text-accent' : 'text-muted hover:text-ink'}>
          {saved ? 'Saved ✓' : 'Save'}
        </button>
        <button type="button" onClick={() => onFeedback(result, rank, 'dismiss')} className="text-muted hover:text-ink">Dismiss</button>
      </div>
      {open && <ExplanationPanel explanation={result.explanation} readiness={result.readiness} />}
    </article>
  )
}
