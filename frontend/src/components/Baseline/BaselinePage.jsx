// S23 (spec 29): plain keyword search, the study's control. No badges, reasons, save, chat, onboarding or
// personalisation. Logs search and view_results only, under condition "baseline".
import { useState } from 'react'
import { baselineSearch } from '../../api.js'
import { useEvents } from '../../hooks/useEvents.js'
import { useStudentId } from '../../hooks/useProfile.js'

function Row({ r }) {
  const [more, setMore] = useState(false)
  const long = r.description.length > 260
  return (
    <article className="rounded border border-line p-4">
      <h3 className="font-semibold">{r.code} {r.title}</h3>
      <p className="text-xs text-muted">{r.credits} credits</p>
      <p className={`mt-2 text-sm ${more || !long ? '' : 'line-clamp-3'}`}>{r.description}</p>
      {long && <button type="button" onClick={() => setMore(!more)} className="text-xs text-accent underline">{more ? 'Show less' : 'Show more'}</button>}
      <p className="mt-2 text-sm text-muted">{r.prerequisites_text || 'No prerequisites listed.'}</p>
    </article>
  )
}

export default function BaselinePage() {
  const [studentId] = useStudentId('baseline')
  const log = useEvents(studentId, 'baseline')
  const [q, setQ] = useState('')
  const [state, setState] = useState({ status: 'idle', data: null })

  const search = async (e) => {
    e.preventDefault()
    const query = q.trim()
    if (!query) return
    setState({ status: 'loading', data: null })
    log('search', { query })
    const r = await baselineSearch(query, 10)
    if (!r.ok) { setState({ status: 'error', data: null }); return }
    setState({ status: 'ok', data: r.data })
    log('view_results', { query, payload: { count: r.data.returned_count } })
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <header className="mb-4 border-b border-line pb-3">
        <h1 className="text-xl font-semibold text-accent">Course search</h1>
      </header>
      <form className="flex gap-2" onSubmit={search}>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search graduate courses by keyword"
          className="flex-1 rounded border border-line px-3 py-2" />
        <button className="rounded bg-accent px-4 py-2 text-white">Search</button>
      </form>
      <div className="mt-4 space-y-3">
        {state.status === 'loading' && <p className="text-muted">Searching…</p>}
        {state.status === 'error' && <p className="text-muted">Could not reach the server.</p>}
        {state.status === 'ok' && !state.data.results.length && <p className="text-muted">No courses matched.</p>}
        {state.status === 'ok' && state.data.results.map((r) => <Row key={r.code} r={r} />)}
      </div>
    </div>
  )
}
