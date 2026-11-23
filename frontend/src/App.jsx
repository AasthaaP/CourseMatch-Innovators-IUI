// Three routes: "/" (the CourseMatch system), "/baseline" (the study control, spec 29) and "/study"
// (the user study flow, final spec Section 11).
import SystemPage from './components/SystemPage/SystemPage.jsx'
import BaselinePage from './components/Baseline/BaselinePage.jsx'
import StudyPage from './components/Study/StudyPage.jsx'

export default function App() {
  const path = window.location.pathname
  if (path.startsWith('/study')) return <StudyPage />
  return path.startsWith('/baseline') ? <BaselinePage /> : <SystemPage />
}
