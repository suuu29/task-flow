import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'pretendard/dist/web/static/Pretendard-Regular.css'
import 'pretendard/dist/web/static/Pretendard-Medium.css'
import 'pretendard/dist/web/static/Pretendard-Bold.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
