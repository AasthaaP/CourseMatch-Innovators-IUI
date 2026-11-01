// S19 (spec 25): three steps on one scrolling page with a step indicator. Also reopened by "Edit profile".
import { useEffect, useMemo, useRef, useState } from 'react'
import { autocomplete, listSamples } from '../../api.js'
import { TOPIC_GROUPS } from '../../topicGroups.js'

// /api/samples carries no program codes, so the options are the one program in program_requirements
// plus Other (spec 5.5 accepts exactly these).
const PROGRAMS = [{ code: 'MSCS', label: 'MS Computer Science' }, { code: 'OTHER', label: 'Other' }]
const DAYS = [['M', 'Mon'], ['T', 'Tue'], ['W', 'Wed'], ['R', 'Thu'], ['F', 'Fri']]
const TERM_NAMES = { SP: 'Spring', SU: 'Summer', FA: 'Fall' }

// The next six terms after today, e.g. in November 2026: 2027SP ... 2028FA.
function nextTerms(now = new Date()) {
  const order = ['SP', 'SU', 'FA']
  let year = now.getFullYear()
  let i = now.getMonth() < 4 ? 1 : now.getMonth() < 7 ? 2 : 0
  if (i === 0) year += 1
  return Array.from({ length: 6 }, () => {
    const term = `${year}${order[i]}`
    i = (i + 1) % 3
    if (i === 0) year += 1
    return term
  })
}
const termLabel = (t) => `${TERM_NAMES[t.slice(4)]} ${t.slice(0, 4)}`

function Step({ n, title, done, children }) {
  return (
    <section className="rounded border border-line p-4">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${done ? 'bg-accent text-white' : 'border border-line text-muted'}`}>
          {done ? '✓' : n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  )
}

function Chip({ on, onClick, children, removable }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={`rounded-full border px-3 py-1 text-sm ${on ? 'border-accent bg-accent text-white' : 'border-line text-ink hover:border-accent'}`}>
      {children}{removable && <span className="ml-1.5" aria-hidden>×</span>}
    </button>
  )
}

export default function Onboarding({ profile, onSave, onLoadSample, onDone, onCancel, log }) {
  const terms = useMemo(() => nextTerms(), [])
  const stated = profile?.stated || {}
  const [program, setProgram] = useState(stated.program || '')
  const [gradTerm, setGradTerm] = useState(stated.graduation_term || '')
  const [credits, setCredits] = useState(stated.credits_per_term ?? 9)
  const [courses, setCourses] = useState(stated.completed_courses || [])
  const [interests, setInterests] = useState(stated.interests || [])
  const [days, setDays] = useState(stated.preferred_days || [])
  const [samples, setSamples] = useState([])
  const [q, setQ] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [titles, setTitles] = useState({})
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const started = useRef(false)

  const fill = (p) => {
    const s = p.stated
    setProgram(s.program || ''); setGradTerm(s.graduation_term || ''); setCredits(s.credits_per_term ?? 9)
    setCourses(s.completed_courses || []); setInterests(s.interests || []); setDays(s.preferred_days || [])
  }

  useEffect(() => {
    if (!started.current) { started.current = true; log('onboard_start') }
    listSamples().then((r) => r.ok && setSamples(r.data.samples))
  }, [log])

  useEffect(() => {  // 250 ms debounce (spec 25.1)
    if (!q.trim()) { setSuggestions([]); return }
    const t = setTimeout(() => autocomplete(q, 8).then((r) => r.ok && setSuggestions(r.data.results)), 250)
    return () => clearTimeout(t)
  }, [q])

  const toggle = (list, setList, v) => setList(list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const addCourse = (c) => {
    if (!courses.includes(c.code)) setCourses([...courses, c.code])
    setTitles((t) => ({ ...t, [c.code]: c.title }))
    setQ(''); setSuggestions([])
  }

  const chooseSample = async (name) => {
    setError(null)
    const r = await onLoadSample(name)
    if (r.ok) fill(r.data)
    else setError('Could not load that sample student.')
  }

  const start = async () => {
    setBusy(true); setError(null)
    const r = await onSave({
      program, graduation_term: gradTerm || null, credits_per_term: Number(credits) || 9,
      completed_courses: courses, interests, preferred_days: days,
    })
    setBusy(false)
    if (r.ok) { log('onboard_complete'); onDone() }
    else if (r.status === 422) {
      const unknown = (r.data?.detail || []).flatMap((d) => d.unknown || [])
      setError(unknown.length ? `Not recognised: ${unknown.join(', ')}` : 'Some answers are not valid. Check each step.')
    } else setError('Could not reach the server.')
  }

  const canStart = Boolean(program) && interests.length > 0 && !busy

  return (
    <div data-testid="onboarding" className="mx-auto max-w-3xl space-y-4">
      <div className="sticky top-0 z-10 -mx-4 flex items-center justify-between border-b border-line bg-white px-4 py-2 text-sm">
        <ol className="flex gap-4 text-muted">
          <li className={program ? 'text-ink' : ''}>1 · Program</li>
          <li className={courses.length ? 'text-ink' : ''}>2 · Courses taken</li>
          <li className={interests.length ? 'text-ink' : ''}>3 · Interests</li>
        </ol>
        {onCancel && <button type="button" onClick={onCancel} className="text-muted underline">Cancel</button>}
      </div>

      <Step n={1} title="Your program" done={Boolean(program)}>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">Degree program
            <select value={program} onChange={(e) => setProgram(e.target.value)} className="mt-1 w-full rounded border border-line px-2 py-1.5">
              <option value="">Choose…</option>
              {PROGRAMS.map((p) => <option key={p.code} value={p.code}>{p.label}</option>)}
            </select>
          </label>
          <label className="text-sm">Graduation term
            <select value={gradTerm} onChange={(e) => setGradTerm(e.target.value)} className="mt-1 w-full rounded border border-line px-2 py-1.5">
              <option value="">Choose…</option>
              {[...new Set([...(gradTerm && !terms.includes(gradTerm) ? [gradTerm] : []), ...terms])].map((t) =>
                <option key={t} value={t}>{termLabel(t)}</option>)}
            </select>
          </label>
          <label className="text-sm">Credits per semester
            <input type="number" min={3} max={15} value={credits} onChange={(e) => setCredits(e.target.value)}
              className="mt-1 w-full rounded border border-line px-2 py-1.5" />
          </label>
        </div>
      </Step>

      <Step n={2} title="Courses you have taken" done={courses.length > 0}>
        <div className="relative">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by code or title, e.g. CSCE 6 or linear algebra"
            className="w-full rounded border border-line px-3 py-2" />
          {suggestions.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full rounded border border-line bg-white text-sm shadow">
              {suggestions.map((s) => (
                <li key={s.code}>
                  <button type="button" onClick={() => addCourse(s)} className="w-full px-3 py-1.5 text-left hover:bg-notsure-bg">
                    <span className="font-medium">{s.code}</span> {s.title}
                    {s.level === 'undergraduate' && <span className="ml-1 text-muted">(undergraduate)</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {courses.map((c) => (
            <Chip key={c} on removable onClick={() => setCourses(courses.filter((x) => x !== c))}>
              {c}{titles[c] ? ` ${titles[c]}` : ''}
            </Chip>
          ))}
        </div>
        <div className="mt-4 border-t border-line pt-3 text-sm">
          <p className="mb-2 font-medium">Load a sample student</p>
          <div className="flex flex-wrap gap-2">
            {samples.map((s) => (
              <button key={s.name} type="button" onClick={() => chooseSample(s.name)}
                className="rounded border border-line px-3 py-1.5 text-left hover:border-accent">
                <span className="font-medium">{s.name}</span>
                <span className="block text-xs text-muted">{s.label}</span>
              </button>
            ))}
          </div>
        </div>
      </Step>

      <Step n={3} title="Your interests" done={interests.length > 0}>
        <div className="space-y-3">
          {TOPIC_GROUPS.map(([heading, topics]) => (
            <div key={heading}>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{heading}</h3>
              <div className="flex flex-wrap gap-2">
                {topics.map((t) => <Chip key={t} on={interests.includes(t)} onClick={() => toggle(interests, setInterests, t)}>{t}</Chip>)}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-2 text-sm font-medium">Preferred days</p>
          <div className="flex gap-2">
            {DAYS.map(([d, label]) => <Chip key={d} on={days.includes(d)} onClick={() => toggle(days, setDays, d)}>{label}</Chip>)}
          </div>
        </div>
      </Step>

      {error && <p className="text-sm text-onefirst-fg">{error}</p>}
      <div className="flex items-center gap-3 pb-8">
        <button type="button" disabled={!canStart} onClick={start}
          className="rounded bg-accent px-6 py-2 text-white disabled:cursor-not-allowed disabled:opacity-40">
          {busy ? 'Saving…' : 'Start'}
        </button>
        {!canStart && !busy && <span className="text-sm text-muted">Choose a program and at least one interest.</span>}
      </div>
    </div>
  )
}
