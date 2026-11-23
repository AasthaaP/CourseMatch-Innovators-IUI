// Final spec 9.2: what the student told us, and what CourseMatch inferred from saves and dismissals.
// Inferred interests can be removed and restored; removal is sticky on the server.
import { useEffect, useState } from 'react'
import { getProfile, patchInference } from '../../api.js'

const DAY_NAMES = { M: 'Mon', T: 'Tue', W: 'Wed', R: 'Thu', F: 'Fri' }
const TERM_NAMES = { SP: 'Spring', SU: 'Summer', FA: 'Fall' }
const PROGRAM_NAMES = { MSCS: 'MS Computer Science', OTHER: 'Other' }
const termLabel = (t) => (t ? `${TERM_NAMES[t.slice(4)] || t.slice(4)} ${t.slice(0, 4)}` : 'Not set')

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-line py-2 last:border-0 sm:grid-cols-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-sm sm:col-span-2">{children}</dd>
    </div>
  )
}

function InferenceRow({ inf, action, onClick, busy }) {
  const phrase = inf.weight > 0 ? `Leaning toward ${inf.value}` : inf.weight < 0 ? `Less interested in ${inf.value}` : inf.value
  return (
    <li className="flex items-start justify-between gap-3 border-b border-line py-2 last:border-0">
      <div>
        <p className="text-sm font-medium">{phrase}</p>
        <p className="text-xs text-muted">Based on: {inf.evidence.length ? inf.evidence.join(', ') : 'nothing yet'}</p>
      </div>
      <button type="button" disabled={busy} onClick={onClick}
        className="shrink-0 rounded border border-line px-3 py-1 text-sm text-accent hover:border-accent disabled:opacity-40">
        {action}
      </button>
    </li>
  )
}

export default function ProfilePage({ studentId, initialProfile, onBack, onEdit, studyMode = false }) {
  const [profile, setProfile] = useState(initialProfile)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [showRemoved, setShowRemoved] = useState(false)
  const [changed, setChanged] = useState(false)  // a Remove or Restore happened on this visit

  useEffect(() => {  // saves and dismissals since the last load may have changed the inferences
    let live = true
    getProfile(studentId).then((r) => { if (live && r.ok) setProfile(r.data) })
    return () => { live = false }
  }, [studentId])

  const toggle = async (inf, active) => {
    setBusy(true); setError(null)
    const r = await patchInference(studentId, inf.id, active)
    setBusy(false)
    if (r.ok) { setProfile(r.data); setChanged(true) }
    else setError('Could not update your profile. Try again.')
  }

  const stated = profile?.stated || {}
  const titles = profile?.course_titles || {}
  const inferred = profile?.inferred || []
  const active = inferred.filter((i) => i.active)
  const removed = inferred.filter((i) => !i.active)

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Your profile</h2>
        <button type="button" onClick={() => onBack(profile, changed)} className="rounded border border-line px-3 py-1 text-sm">
          Back to results
        </button>
      </div>

      <section className="mb-6 rounded border border-line p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold">What you told us</h3>
          {!studyMode && onEdit && (
            <button type="button" onClick={onEdit} className="text-sm text-accent underline">Edit</button>
          )}
        </div>
        <dl>
          <Row label="Program">{PROGRAM_NAMES[stated.program] || stated.program || 'Not set'}</Row>
          <Row label="Graduating">{termLabel(stated.graduation_term)}</Row>
          <Row label="Credits per semester">{stated.credits_per_term ?? 'Not set'}</Row>
          <Row label="Preferred days">
            {stated.preferred_days?.length ? stated.preferred_days.map((d) => DAY_NAMES[d] || d).join(', ') : 'Any'}
          </Row>
          <Row label="Courses taken">
            {stated.completed_courses?.length ? (
              <ul>{stated.completed_courses.map((c) => <li key={c}>{c} {titles[c] || ''}</li>)}</ul>
            ) : 'None'}
          </Row>
          <Row label="Interests">{stated.interests?.length ? stated.interests.join(', ') : 'None'}</Row>
        </dl>
      </section>

      <section className="rounded border border-line p-4">
        <h3 className="font-semibold">What CourseMatch worked out from your saves and dismissals</h3>
        <p className="mb-2 text-sm text-muted">These guesses adjust your rankings. Remove any that are wrong.</p>
        {error && <p className="mb-2 text-sm text-onefirst-fg">{error}</p>}
        {!inferred.length ? (
          <p className="text-sm text-muted">Nothing yet. Save or dismiss courses and CourseMatch will show what it learns here.</p>
        ) : (
          <>
            {active.length > 0 && (
              <ul>{active.map((i) => <InferenceRow key={i.id} inf={i} action="Remove" busy={busy} onClick={() => toggle(i, false)} />)}</ul>
            )}
            {removed.length > 0 && (
              <div className="mt-3">
                <button type="button" onClick={() => setShowRemoved(!showRemoved)} aria-expanded={showRemoved}
                  className="text-sm text-muted underline">
                  {showRemoved ? '▾' : '▸'} Removed by you ({removed.length})
                </button>
                {showRemoved && (
                  <ul className="mt-1">{removed.map((i) => <InferenceRow key={i.id} inf={i} action="Restore" busy={busy} onClick={() => toggle(i, true)} />)}</ul>
                )}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
