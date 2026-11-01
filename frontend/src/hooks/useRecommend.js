import { useCallback, useState } from 'react'
import { recommend } from '../api.js'

// state.status: idle | loading | ok | error. state.error carries the API error code
// ('index_not_ready', 'network', ...) so ResultList can show the right 26.4 state.
export function useRecommend(studentId) {
  const [state, setState] = useState({ status: 'idle', data: null, error: null, query: '' })
  const run = useCallback(async (query, opts) => {
    setState((s) => ({ ...s, status: 'loading', query }))
    const r = await recommend(studentId, query, opts)
    if (r.ok) setState({ status: 'ok', data: r.data, error: null, query })
    else setState({ status: 'error', data: null, error: r.error, query })
  }, [studentId])
  return { state, run }
}
