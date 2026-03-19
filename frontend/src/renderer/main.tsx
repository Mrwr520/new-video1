import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'
import { App } from './App'

// Polyfill for crypto.getRandomValues in Electron renderer process
if (typeof window !== 'undefined' && !window.crypto) {
  (window as any).crypto = {
    getRandomValues: (array: Uint8Array) => {
      for (let i = 0; i < array.length; i++) {
        array[i] = Math.floor(Math.random() * 256)
      }
      return array
    }
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
