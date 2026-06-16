import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useClipboard } from './useClipboard'

describe('useClipboard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('copies text to clipboard', async () => {
    const { result } = renderHook(() => useClipboard())

    await act(async () => {
      await result.current.copyToClipboard('hello world')
    })

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('hello world')
  })

  it('sets copied to true after a successful copy', async () => {
    const { result } = renderHook(() => useClipboard())

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })

    expect(result.current.copied).toBe(true)
  })

  it('resets copied to false after the timeout', async () => {
    const { result } = renderHook(() => useClipboard())

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })
    expect(result.current.copied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current.copied).toBe(false)
  })

  it('respects a custom timeout', async () => {
    const { result } = renderHook(() => useClipboard({ timeout: 5000 }))

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })
    expect(result.current.copied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(result.current.copied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.copied).toBe(false)
  })

  it('calls onSuccess after a successful copy', async () => {
    const onSuccess = vi.fn()
    const { result } = renderHook(() => useClipboard({ onSuccess }))

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })

    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('calls onError when clipboard.writeText rejects', async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'))
    const onError = vi.fn()
    const { result } = renderHook(() => useClipboard({ onError }))

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })

    expect(onError).toHaveBeenCalledTimes(1)
    expect(result.current.copied).toBe(false)
  })

  it('clears the timeout on unmount', async () => {
    const { result, unmount } = renderHook(() => useClipboard())

    await act(async () => {
      await result.current.copyToClipboard('hello')
    })

    unmount()

    expect(() => {
      act(() => {
        vi.advanceTimersByTime(2000)
      })
    }).not.toThrow()
  })
})
