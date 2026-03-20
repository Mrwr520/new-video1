import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTypewriter, useCountUp, KEYFRAMES } from './animations'

describe('useTypewriter', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns empty string initially for non-empty text', () => {
    const { result } = renderHook(() => useTypewriter('hello', 50))
    expect(result.current).toBe('')
  })

  it('progressively reveals text character by character', () => {
    const { result } = renderHook(() => useTypewriter('abc', 100))

    expect(result.current).toBe('')

    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('a')

    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('ab')

    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('abc')
  })

  it('returns empty string for empty input', () => {
    const { result } = renderHook(() => useTypewriter('', 50))
    expect(result.current).toBe('')
  })

  it('resets when text changes', () => {
    const { result, rerender } = renderHook(
      ({ text }) => useTypewriter(text, 100),
      { initialProps: { text: 'ab' } }
    )

    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('a')

    rerender({ text: 'xy' })
    expect(result.current).toBe('')

    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('x')
  })
})

describe('useCountUp', () => {
  it('starts at 0', () => {
    const { result } = renderHook(() => useCountUp(100, 1000))
    expect(result.current).toBe(0)
  })

  it('reaches target value after duration', async () => {
    // useCountUp relies on requestAnimationFrame + performance.now which
    // don't behave reliably under jsdom fake timers. Instead we verify
    // the hook eventually converges using real timers with a generous timeout.
    vi.useRealTimers()
    const { result } = renderHook(() => useCountUp(50, 100))

    await waitFor(() => {
      expect(result.current).toBeGreaterThanOrEqual(48)
    }, { timeout: 2000 })
  })

  it('returns 0 when target is 0', () => {
    const { result } = renderHook(() => useCountUp(0, 500))
    expect(result.current).toBe(0)
  })
})

describe('KEYFRAMES', () => {
  it('has fadeIn keyframe', () => {
    expect(KEYFRAMES.fadeIn).toContain('@keyframes fadeIn')
    expect(KEYFRAMES.fadeIn).toContain('opacity')
  })

  it('has slideUp keyframe', () => {
    expect(KEYFRAMES.slideUp).toContain('@keyframes slideUp')
    expect(KEYFRAMES.slideUp).toContain('translateY')
  })

  it('has pulse keyframe', () => {
    expect(KEYFRAMES.pulse).toContain('@keyframes pulse')
    expect(KEYFRAMES.pulse).toContain('scale')
  })

  it('has spin keyframe', () => {
    expect(KEYFRAMES.spin).toContain('@keyframes spin')
    expect(KEYFRAMES.spin).toContain('rotate')
  })

  it('contains all four expected keys', () => {
    expect(Object.keys(KEYFRAMES)).toEqual(['fadeIn', 'slideUp', 'pulse', 'spin'])
  })
})
