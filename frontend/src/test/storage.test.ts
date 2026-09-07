import { describe, expect, it } from 'vitest'

// These globals must be browser Storage, not Node's optional disk-backed API.
describe('browser storage test environment', () => {
  it.each(['localStorage', 'sessionStorage'] as const)('%s supports browser persistence', (name) => {
    const storage = globalThis[name]
    expect(storage).toBeInstanceOf(Storage)
    expect(storage).toBe(window[name])

    const key = 'storage-environment-regression'
    try {
      storage.setItem(key, 'dark')
      expect(storage.getItem(key)).toBe('dark')
      storage.removeItem(key)
      expect(storage.getItem(key)).toBeNull()
    } finally {
      storage.removeItem(key)
    }
  })
})
