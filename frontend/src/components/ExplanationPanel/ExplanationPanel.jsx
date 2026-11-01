// S21 (spec 27): factors, then "From the catalog" and "Our estimate" in visibly different blocks, so a
// student can tell at a glance which statements come from the university and which the system made.
import SimText from '../SimText.jsx'

export default function ExplanationPanel({ explanation, readiness }) {
  return (
    <div data-testid="why-this-panel" className="mt-3 space-y-3 border-t border-line pt-3 text-sm">
      <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1">
        {explanation.factors.map((f) => (
          <div key={f.kind + f.label} className="contents">
            <dt className="text-muted">{f.label}</dt>
            <dd><SimText text={f.detail} /></dd>
          </div>
        ))}
        {readiness?.path_hint && (
          <div className="contents">
            <dt className="text-muted">Next step</dt>
            <dd><SimText text={readiness.path_hint} /></dd>
          </div>
        )}
      </dl>

      <section className="rounded border-l-4 border-accent bg-white px-3 py-2 ring-1 ring-line">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-accent">From the catalog</h4>
        {explanation.from_catalog.length > 0
          ? explanation.from_catalog.map((t) => <p key={t} className="mt-1 text-ink">“{t}”</p>)
          : <p className="mt-1 text-muted">The catalog lists no prerequisite for this course.</p>}
      </section>

      <section className="rounded border border-dashed border-line bg-notsure-bg px-3 py-2 text-xs text-muted">
        <h4 className="font-semibold uppercase tracking-wide">Our estimate</h4>
        {explanation.our_estimate.map((t) => <p key={t} className="mt-1 italic">{t}</p>)}
      </section>
    </div>
  )
}
