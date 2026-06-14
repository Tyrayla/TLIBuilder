import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import logoSrc from './assets/logo.png'
import './index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    {/* Fixed (out-of-flow) drag strip — does NOT touch the #root/.screen height chain.
        Native min/max/close buttons float over its right side via titleBarOverlay. */}
    <div className="titlebar">
      <img src={logoSrc} className="titlebar-logo" alt="" />
      <span>TLI Builder</span>
    </div>
    <App />
  </React.StrictMode>
)
