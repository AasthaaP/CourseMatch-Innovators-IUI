// One function per endpoint in spec Section 5. Every call resolves to { ok, data } or
// { ok: false, status, error } — never throws — so a dead backend shows an error state, not a blank page.
// VITE_USE_FIXTURES=true serves data/fixtures/api_fixtures.json after 200 ms (spec 7.4, 24.2).
import fixtures from '../../data/fixtures/api_fixtures.json'

const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000').replace(/\/$/, '')
export const USE_FIXTURES = String(import.meta.env.VITE_USE_FIXTURES) === 'true'

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

async function fromFixture(key) {
  await delay(200)
  return { ok: true, data: structuredClone(fixtures[key]) }
}

async function call(method, path, body) {
  try {
    const res = await fetch(BASE + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) return { ok: false, status: res.status, error: data?.error || 'http_error', data }
    return { ok: true, data }
  } catch (error) {
    return { ok: false, status: 0, error: 'network', message: String(error) }
  }
}

const qs = (o) => new URLSearchParams(o).toString()

export const health = () => (USE_FIXTURES ? fromFixture('health') : call('GET', '/api/health'))

export const createSession = (condition = 'system') =>
  USE_FIXTURES
    ? fromFixture('session').then((r) => ({ ...r, data: { ...r.data, condition } }))
    : call('POST', '/api/session', { condition })

export const getProfile = (id) => (USE_FIXTURES ? fromFixture('profile') : call('GET', `/api/profile/${id}`))

export const putProfile = (id, stated) =>
  USE_FIXTURES ? fromFixture('profile') : call('PUT', `/api/profile/${id}`, stated)

export const patchInference = (id, inferenceId, active) =>
  USE_FIXTURES ? fromFixture('profile') : call('PATCH', `/api/profile/${id}/inferences/${inferenceId}`, { active })

export const listSamples = () => (USE_FIXTURES ? fromFixture('samples') : call('GET', '/api/samples'))

export const loadSample = (name, studentId) =>
  USE_FIXTURES ? fromFixture('profile') : call('POST', `/api/samples/${name}/load`, { student_id: studentId })

export const autocomplete = (q, limit = 10, { recommendableOnly = false } = {}) =>
  USE_FIXTURES
    ? fromFixture('autocomplete')
    : call('GET', `/api/courses/autocomplete?${qs({ q, limit, ...(recommendableOnly ? { recommendable_only: true } : {}) })}`)

export const recommend = (studentId, query, { topK = 10, clarificationAnswer = null } = {}) =>
  USE_FIXTURES
    ? fromFixture(query === fixtures.recommend_clarification?.query ? 'recommend_clarification' : 'recommend').then((r) =>
        clarificationAnswer ? { ...r, data: { ...r.data, clarification: null } } : r)
    : call('POST', '/api/recommend', {
        student_id: studentId, query, top_k: topK, clarification_answer: clarificationAnswer,
      })

export const chat = (studentId, message) =>
  USE_FIXTURES ? fromFixture('chat') : call('POST', '/api/chat', { student_id: studentId, message })

export const feedback = (studentId, courseCode, action) =>
  USE_FIXTURES
    ? fromFixture('feedback')
    : call('POST', '/api/feedback', { student_id: studentId, course_code: courseCode, action })

// Fire-and-forget: logging must never break the interface (spec 5.12).
export const logEvent = (evt) =>
  USE_FIXTURES ? Promise.resolve({ ok: true }) : call('POST', '/api/events', evt).catch(() => ({ ok: true }))

// The server logs the baseline search (with the returned codes) when student_id is passed (final spec 10.5).
export const baselineSearch = (q, topK = 10, studentId = null) =>
  USE_FIXTURES
    ? fromFixture('baseline')
    : call('GET', `/api/baseline/search?${qs({ q, top_k: topK, ...(studentId ? { student_id: studentId } : {}) })}`)

// User study (final spec 10.4). Every call resolves to { ok, data } or { ok: false, status, error }.
export const study = {
  config: () => call('GET', '/api/study/config'),
  start: (code) => call('POST', '/api/study/start', { participant_code: code }),
  progress: (code) => call('GET', `/api/study/progress/${encodeURIComponent(code)}`),
  consent: (code) => call('POST', '/api/study/consent', { participant_code: code }),
  taskStart: (code, taskId) => call('POST', '/api/study/task/start', { participant_code: code, task_id: taskId }),
  taskSubmit: (code, taskId, courseCodes) =>
    call('POST', '/api/study/task/submit', { participant_code: code, task_id: taskId, course_codes: courseCodes }),
  questionnaire: (code, taskId, responses) =>
    call('POST', '/api/study/questionnaire', { participant_code: code, task_id: taskId, responses }),
  breakDone: (code) => call('POST', '/api/study/break_done', { participant_code: code }),
  final: (code, answers) => call('POST', '/api/study/final', { participant_code: code, answers }),
}
