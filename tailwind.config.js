/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './frontend/src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        accent: '#500000',
        line: '#C7CBD1',
        ink: '#24262B',
        muted: '#6B7280',
        ready: { fg: '#2E7D4F', bg: '#EAF3EE' },
        onefirst: { fg: '#B4690E', bg: '#FBF2E4' },
        notsure: { fg: '#78808B', bg: '#F1F3F5' },
      },
    },
  },
  plugins: [],
}
