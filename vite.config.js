import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// index.html lives at the repo root; app code is in frontend/src (spec 7.2).
// envDir 'frontend' means VITE_* variables are read from frontend/.env.
export default defineConfig({
  plugins: [react()],
  envDir: 'frontend',
  server: { port: 3000, strictPort: true },
})
