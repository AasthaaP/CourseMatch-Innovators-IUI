// S20 list (spec 26.4 states, 26.5 events and the inference line with Undo).
import { useEffect, useState } from 'react'
import { feedback } from '../../api.js'
import ResultCard from '../ResultCard/ResultCard.jsx'

const REVERSE = { save: 'unsave', dismiss: 'undo_dismiss', unsave: 'save', undo_dismiss: 'dismiss' }

export function ExampleChips({ examples, onSearch, exclude }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {examples.filter((q) => q !== exclude).map((q) => (
        <button key={q} type="button" onClick={() => onSearch(q)} className="rounded-full border border-line px-3 py-1 text-sm text-muted hover:border-accent">
          {q}
        </button>
      ))}
    </div>
  )
}

export default function ResultList({ state, studentId, onRetry, onSearch, examples, log }) {
  const results = state.data?.results || []
  const [marks, setMarks] = useState({})        // code -> 'saved' | 'dismissed'
  const [inference, setInference] = useState(null) // { value, code, undo, rank }

  useEffect(() => {  // new results: start from the server's saved flags, log view_results
    if (state.status !== 'ok') return
    setMarks(Object.fromEntries(results.filter((r) => r.saved).map((r) => [r.code, 'saved'])))
    log('view_results', { query: state.query, payload: { count: results.length, personalized: state.data.personalized } })
  }, [state.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (result, rank, action) => {
    log(action, { courseCode: result.code, query: state.query, payload: { rank } })
    const r = await feedback(studentId, result.code, action)
    if (!r.ok) return
    setMarks((m) => {
      const next = { ...m }
      if (action === 'save') next[result.code] = 'saved'
      else if (action === 'dismiss') next[result.code] = 'dismissed'
      else delete next[result.code]
      return next
    })
    const changed = r.data.inference_changed
    if (changed && (action === 'save' || action === 'dismiss')) {
      setInference({ value: changed.value, result, rank, undo: REVERSE[action] })
    } else if (action === 'unsave' || action === 'undo_dismiss') {
      setInference((cur) => (cur?.result.code === result.code ? null : cur))
    }
  }

  if (state.status === 'idle') return null
  if (state.status === 'loading')
    return <div className="space-y-3" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="h-24 rounded border border-line bg-notsure-bg" />)}</div>
  if (state.status === 'error') {
    if (state.error === 'index_not_ready')
      return <p className="text-muted">The course index has not been built. Run scripts/build_index.py.</p>
    return (
      <p className="text-muted">
        Could not reach the server. <button type="button" onClick={onRetry} className="text-accent underline">Retry</button>
      </p>
    )
  }
  if (!results.length)
    return (
      <div>
        <p className="text-muted">No courses matched. Try a broader search or remove an interest.</p>
        <ExampleChips examples={examples} onSearch={onSearch} exclude={state.query} />
      </div>
    )

  return (
    <div className="space-y-3">
      {inference && (
        <p className="rounded bg-notsure-bg px-3 py-2 text-sm">
          Updated what we think you are interested in: {inference.value}.{' '}
          <button type="button" className="text-accent underline"
            onClick={() => { send(inference.result, inference.rank, inference.undo); setInference(null) }}>
            Undo
          </button>
        </p>
      )}
      {results.map((r, i) =>
        marks[r.code] === 'dismissed' ? (
          <p key={r.code} className="rounded border border-dashed border-line px-4 py-2 text-sm text-muted">
            Dismissed {r.code} {r.title}.{' '}
            <button type="button" className="text-accent underline" onClick={() => send(r, i + 1, 'undo_dismiss')}>Undo</button>
          </p>
        ) : (
          <ResultCard key={r.code} result={r} rank={i + 1} saved={marks[r.code] === 'saved'} onFeedback={send} log={log} />
        ),
      )}
    </div>
  )
}
