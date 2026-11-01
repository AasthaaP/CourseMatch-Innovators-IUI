import { useCallback, useEffect, useState } from 'react'
import { createSession, getProfile, loadSample as apiLoadSample, putProfile } from '../api.js'

const KEY = 'coursematch_student_id'

// Spec 24.3: read the id from localStorage, otherwise create one via /api/session.
// reset() forgets a stale id (e.g. after the database was rebuilt) and creates a new one.
export function useStudentId(condition = 'system') {
  const key = condition === 'baseline' ? `${KEY}_baseline` : KEY
  const [id, setId] = useState(() => {
    try { return localStorage.getItem(key) } catch { return null }
  })
  useEffect(() => {
    if (id) return
    createSession(condition).then((r) => {
      if (!r.ok) return
      try { localStorage.setItem(key, r.data.student_id) } catch { /* private mode */ }
      setId(r.data.student_id)
    })
  }, [id, key, condition])
  const reset = useCallback(() => {
    try { localStorage.removeItem(key) } catch { /* private mode */ }
    setId(null)
  }, [key])
  return [id, reset]
}

// S13/S19: the student's profile, read once the id is known, written by onboarding.
export function useProfile(studentId, onUnknownStudent) {
  const [state, setState] = useState({ status: 'loading', profile: null, error: null })

  useEffect(() => {
    if (!studentId) return
    let live = true
    getProfile(studentId).then((r) => {
      if (!live) return
      if (r.ok) setState({ status: 'ok', profile: r.data, error: null })
      else if (r.status === 404) onUnknownStudent?.()
      else setState({ status: 'error', profile: null, error: r.error })
    })
    return () => { live = false }
  }, [studentId, onUnknownStudent])

  const save = useCallback(async (stated) => {
    const r = await putProfile(studentId, stated)
    if (r.ok) setState({ status: 'ok', profile: r.data, error: null })
    return r
  }, [studentId])

  const loadSample = useCallback(async (name) => {
    const r = await apiLoadSample(name, studentId)
    if (r.ok) setState({ status: 'ok', profile: r.data, error: null })
    return r
  }, [studentId])

  return { ...state, save, loadSample }
}
