import React from 'react'
import ReactDOM from 'react-dom/client'
import ViewApp from './view/ViewApp'
import ErrorBoundary from './components/ErrorBoundary'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ViewApp />
    </ErrorBoundary>
  </React.StrictMode>
)
