import { useCallback } from 'react'
import { logEvent } from '../api.js'

// Spec 23.2: the interface logs onboard_*, view_results, expand/collapse, save/unsave,
// dismiss/undo_dismiss, clarify_answered/clarify_dismissed. Include the card's rank in payload.
export function useEvents(studentId, condition = 'system') {
  return useCallback(
    (event, { courseCode = null, query = null, payload = null } = {}) =>
      logEvent({ student_id: studentId, condition, event, course_code: courseCode, query, payload }),
    [studentId, condition],
  )
}
