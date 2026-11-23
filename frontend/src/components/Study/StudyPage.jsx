// The study flow at /study (final spec Section 11): code entry, consent, practice, two scored tasks with a
// questionnaire after each, a break, final questions, done. Progress lives on the server, so a reload resumes
// at next_step. The condition name, scores and feasibility are never shown.
import { useCallback, useEffect, useRef, useState } from 'react'
import { autocomplete, study } from '../../api.js'
import SystemPage from '../SystemPage/SystemPage.jsx'
import BaselinePage from '../Baseline/BaselinePage.jsx'

const CODE_KEY = 'coursematch_study_code'
const NETWORK = 'Could not reach the server. Your progress is saved. Try again.'
const CONSENT = 'This study is part of a CSCE 634 class project at Texas A&M. You will use two course search interfaces to pick courses for example students. It takes about 35 minutes. We record what you click, search and type in the study, and your answers to a short questionnaire. We do not collect your name, your own courses, or any personal academic records. Your participant code is the only identifier. You can stop at any time by closing the page.'
const PROGRAM_NAMES = { MSCS: 'MS Computer Science', OTHER: 'Other' }

const readCode = () => { try { return localStorage.getItem(CODE_KEY) } catch { return null } }
const writeCode = (c) => { try { c ? localStorage.setItem(CODE_KEY, c) : localStorage.removeItem(CODE_KEY) } catch { /* private mode */ } }

function Card({ title, children }) {
  return (
    <div className="mx-auto mt-10 max-w-2xl rounded border border-line p-6">
      {title && <h1 className="mb-4 text-xl font-semibold text-accent">{title}</h1>}
      {children}
    </div>
  )
}

function Button({ children, disabled, onClick, type = 'button' }) {
  return (
    <button type={type} disabled={disabled} onClick={onClick}
      className="rounded bg-accent px-4 py-2 text-white disabled:opacity-40">{children}</button>
  )
}

function NetworkError({ onRetry }) {
  return (
    <Card>
      <p className="mb-4">{NETWORK}</p>
      <Button onClick={onRetry}>Retry</Button>
    </Card>
  )
}

// ---------------------------------------------------------------- answer bar
function CourseField({ label, value, onChange }) {
  const [text, setText] = useState(value ? `${value.code} ${value.title}` : '')
  const [options, setOptions] = useState([])
  const [open, setOpen] = useState(false)
  const timer = useRef(null)

  const search = (q) => {
    setText(q); onChange(null); setOpen(true)
    clearTimeout(timer.current)
    if (!q.trim()) { setOptions([]); return }
    timer.current = setTimeout(async () => {
      const r = await autocomplete(q, 8, { recommendableOnly: true })
      if (r.ok) setOptions(r.data.results)
    }, 150)
  }
  const pick = (o) => { onChange({ code: o.code, title: o.title }); setText(`${o.code} ${o.title}`); setOpen(false) }

  return (
    <label className="relative block min-w-0 flex-1 text-xs text-muted">
      {label}
      <input value={text} onChange={(e) => search(e.target.value)} onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} placeholder="Type a code or title"
        className={`mt-1 w-full rounded border px-2 py-1.5 text-sm text-ink ${value ? 'border-ready-fg' : 'border-line'}`} />
      {open && options.length > 0 && !value && (
        <ul className="absolute z-40 mt-1 max-h-60 w-full overflow-y-auto rounded border border-line bg-white text-sm text-ink shadow">
          {options.map((o) => (
            <li key={o.code}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(o)}
                className="w-full px-2 py-1.5 text-left hover:bg-notsure-bg">{o.code} {o.title}</button>
            </li>
          ))}
        </ul>
      )}
    </label>
  )
}

function TaskScreen({ code, task, onSubmitted, onNetworkError }) {
  const [answers, setAnswers] = useState(() => Array(task.required).fill(null))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const codes = answers.map((a) => a?.code).filter(Boolean)
  const ready = codes.length === task.required && new Set(codes).size === task.required

  const submit = async () => {
    setBusy(true); setError(null)
    const r = await study.taskSubmit(code, task.task_id, codes)
    setBusy(false)
    if (r.ok) onSubmitted(r.data)
    else if (r.status === 0) onNetworkError(submit)
    else setError(`Choose ${task.required} different courses from the list.`)
  }

  const p = task.profile
  return (
    <div>
      <div className="sticky top-0 z-20 border-b border-line bg-white px-4 py-3 shadow-sm">
        <div className="mx-auto max-w-6xl text-sm">
          <p className="font-medium">{task.prompt}</p>
          <div className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-muted">
            <span>This student's program: {PROGRAM_NAMES[p.program] || p.program}</span>
            <span>Courses already taken: {p.completed_courses.map((c) => `${c.code} ${c.title}`).join('; ') || 'none'}</span>
            <span>Interests: {p.interests.join(', ')}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            {answers.map((a, i) => (
              <CourseField key={i} label={`Course ${i + 1}`} value={a}
                onChange={(v) => setAnswers((cur) => cur.map((x, j) => (j === i ? v : x)))} />
            ))}
            <Button disabled={!ready || busy} onClick={submit}>Submit</Button>
          </div>
          {codes.length === task.required && !ready && <p className="mt-1 text-xs text-onefirst-fg">Choose different courses.</p>}
          {error && <p className="mt-1 text-xs text-onefirst-fg">{error}</p>}
        </div>
      </div>
      {task.condition === 'system'
        ? <SystemPage key={task.student_id} studentIdOverride={task.student_id} studyMode />
        : <BaselinePage key={task.student_id} studentIdOverride={task.student_id} studyMode />}
    </div>
  )
}

// ---------------------------------------------------------------- questionnaire, break, final
function Questionnaire({ config, onSubmit, busy }) {
  const [values, setValues] = useState({})
  const { min, max, min_label: minLabel, max_label: maxLabel } = config.scale
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i)
  const done = config.questionnaire.every((q) => values[q.id] != null)
  return (
    <Card title="About the interface you just used">
      <div className="space-y-5">
        {config.questionnaire.map((q) => (
          <fieldset key={q.id}>
            <legend className="mb-2 text-sm font-medium">{q.text}</legend>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="w-20 text-right">{minLabel}</span>
              {points.map((n) => (
                <label key={n} className="flex flex-col items-center">
                  <input type="radio" name={q.id} value={n} checked={values[q.id] === n}
                    onChange={() => setValues((v) => ({ ...v, [q.id]: n }))} />
                  {n}
                </label>
              ))}
              <span className="w-20">{maxLabel}</span>
            </div>
          </fieldset>
        ))}
      </div>
      <div className="mt-6"><Button disabled={!done || busy} onClick={() => onSubmit(values)}>Continue</Button></div>
    </Card>
  )
}

function FinalQuestions({ config, onSubmit, busy }) {
  const [answers, setAnswers] = useState({})
  return (
    <Card title="A few last questions">
      <div className="space-y-4">
        {config.final_questions.map((q) => (
          <label key={q.id} className="block text-sm">
            {q.text}
            <textarea rows={3} value={answers[q.id] || ''} onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
              className="mt-1 w-full rounded border border-line px-2 py-1.5" />
          </label>
        ))}
      </div>
      <div className="mt-4"><Button disabled={busy} onClick={() => onSubmit(answers)}>Submit</Button></div>
    </Card>
  )
}

// ---------------------------------------------------------------- the flow
export default function StudyPage() {
  const [code, setCode] = useState(readCode)
  const [input, setInput] = useState('')
  const [progress, setProgress] = useState(null)
  const [config, setConfig] = useState(null)
  const [task, setTask] = useState(null)
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [retry, setRetry] = useState(null)  // set on a network error: the action to try again

  const step = progress?.next_step
  const fail = useCallback((again) => setRetry(() => again), [])

  // One server call; network errors show the Retry screen, other errors a short message.
  const act = useCallback(async (fn, onOk) => {
    setBusy(true); setMessage(null)
    const r = await fn()
    setBusy(false)
    if (r.ok) { setRetry(null); onOk(r.data); return r }
    if (r.status === 0) fail(() => act(fn, onOk))
    return r
  }, [fail])

  useEffect(() => {  // resume a stored code
    if (!code || progress) return
    act(() => study.progress(code), setProgress).then((r) => {
      if (!r.ok && r.status === 404) { writeCode(null); setCode(null) }
    })
  }, [code, progress, act])

  useEffect(() => {
    if (config) return
    act(() => study.config(), setConfig)
  }, [config, act])

  useEffect(() => {  // entering a task step starts (or resumes) its session
    if (!code || !step) return
    const taskId = step === 'practice' ? 'practice' : step.startsWith('task:') ? step.slice(5) : null
    if (!taskId) { setTask(null); return }
    if (task?.task_id === taskId) return
    act(() => study.taskStart(code, taskId), setTask).then((r) => {
      if (!r.ok && r.status !== 0) act(() => study.progress(code), setProgress)  // stale step: resync
    })
  }, [code, step, task, act])

  if (retry) return <NetworkError onRetry={() => retry()} />

  if (!code || !progress) {
    const start = async (e) => {
      e.preventDefault()
      const c = input.trim().toUpperCase()
      if (!c) return
      const r = await act(() => study.start(c), (data) => { writeCode(c); setCode(c); setProgress(data) })
      if (!r.ok && r.status === 422) setMessage('That code is not valid. Codes look like P001.')
    }
    if (code && !progress) return <p className="p-6 text-muted">Loading…</p>
    return (
      <Card title="CourseMatch study">
        <form onSubmit={start} className="flex flex-wrap items-end gap-2">
          <label className="text-sm">
            Participant code
            <input value={input} onChange={(e) => setInput(e.target.value)} autoFocus
              className="mt-1 block rounded border border-line px-2 py-1.5" />
          </label>
          <Button type="submit" disabled={busy || !input.trim()}>Start</Button>
        </form>
        {message && <p className="mt-2 text-sm text-onefirst-fg">{message}</p>}
      </Card>
    )
  }

  if (step === 'consent') {
    return (
      <Card title="CourseMatch study">
        <p className="mb-4 text-sm leading-relaxed">{CONSENT}</p>
        <label className="mb-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          I have read this and agree to take part
        </label>
        <Button disabled={!agree || busy} onClick={() => act(() => study.consent(code), setProgress)}>Continue</Button>
      </Card>
    )
  }

  if (step === 'practice' || step?.startsWith('task:')) {
    const taskId = step === 'practice' ? 'practice' : step.slice(5)
    if (!task || task.task_id !== taskId) return <p className="p-6 text-muted">Loading…</p>
    return <TaskScreen key={task.student_id} code={code} task={task}
      onSubmitted={(p) => { setTask(null); setProgress(p); window.scrollTo(0, 0) }}
      onNetworkError={(again) => fail(again)} />
  }

  if (step?.startsWith('questionnaire:')) {
    if (!config) return <p className="p-6 text-muted">Loading…</p>
    return <Questionnaire key={step} config={config} busy={busy}
      onSubmit={(values) => act(() => study.questionnaire(code, step.slice(14), values), setProgress)} />
  }

  if (step === 'break') {
    return (
      <Card>
        <p className="mb-4">Take a short break if you want. The next task uses a different interface.</p>
        <Button disabled={busy} onClick={() => act(() => study.breakDone(code), setProgress)}>Continue</Button>
      </Card>
    )
  }

  if (step === 'final') {
    if (!config) return <p className="p-6 text-muted">Loading…</p>
    return <FinalQuestions config={config} busy={busy} onSubmit={(answers) => act(() => study.final(code, answers), setProgress)} />
  }

  return (
    <Card>
      <p>Thank you. You can close this page.</p>
    </Card>
  )
}
