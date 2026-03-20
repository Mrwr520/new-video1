import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * Typewriter effect hook - progressively reveals text character by character.
 * Validates: Requirements 5.3, 5.4
 */
export function useTypewriter(text: string, speed: number = 50): string {
  const [displayed, setDisplayed] = useState('')
  const indexRef = useRef(0)

  useEffect(() => {
    setDisplayed('')
    indexRef.current = 0

    if (!text) return

    const interval = setInterval(() => {
      indexRef.current += 1
      const next = text.slice(0, indexRef.current)
      setDisplayed(next)

      if (indexRef.current >= text.length) {
        clearInterval(interval)
      }
    }, speed)

    return () => clearInterval(interval)
  }, [text, speed])

  return displayed
}

/**
 * Count-up animation hook - animates a number from 0 to target using requestAnimationFrame.
 * Validates: Requirements 5.5, 5.6
 */
export function useCountUp(target: number, duration: number = 1000): number {
  const [value, setValue] = useState(0)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === 0) {
      setValue(0)
      return
    }

    const startTime = performance.now()

    const animate = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // ease-out quad
      const eased = 1 - (1 - progress) * (1 - progress)
      setValue(Math.round(eased * target))

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [target, duration])

  return value
}

/**
 * CSS @keyframes definitions for common animation effects.
 * These can be injected into <style> tags for use with CSS animation properties.
 */
export const KEYFRAMES = {
  fadeIn: `@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}`,
  slideUp: `@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}`,
  pulse: `@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}`,
  spin: `@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}`
} as const
