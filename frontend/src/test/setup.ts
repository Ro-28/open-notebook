/// <reference types="vitest/jsdom" />
import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Node's native Web Storage can shadow jsdom (and be unavailable without
// --localstorage-file). Stores must capture this test window's real Storage.
vi.stubGlobal('localStorage', jsdom.window.localStorage)
vi.stubGlobal('sessionStorage', jsdom.window.sessionStorage)

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: vi.fn(() => ''),
  useSearchParams: () => new URLSearchParams(),
}))

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated
    removeListener: vi.fn(), // Deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock @/lib/hooks/use-translation with standard t() function
vi.mock('../lib/hooks/use-translation', () => {
  return {
    useTranslation: () => ({
      t: (key: string) => key,
      language: 'en-US',
      setLanguage: vi.fn(),
    }),
  }
})

// Mock @/lib/hooks/use-auth
vi.mock('@/lib/hooks/use-auth', () => ({
  useAuth: vi.fn(() => ({
    user: { id: '1', email: 'test@example.com' },
    logout: vi.fn(),
    isLoading: false,
  })),
}))

// Mock @/lib/stores/sidebar-store
vi.mock('@/lib/stores/sidebar-store', () => ({
  useSidebarStore: vi.fn(() => ({
    isCollapsed: false,
    toggleCollapse: vi.fn(),
  })),
}))

// Mock @/lib/hooks/use-create-dialogs
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: vi.fn(() => ({
    openSourceDialog: vi.fn(),
    openNotebookDialog: vi.fn(),
    openPodcastDialog: vi.fn(),
  })),
}))

// Mock @/lib/hooks/use-launcher (local launcher quit button; needs a QueryClient otherwise)
vi.mock('@/lib/hooks/use-launcher', () => ({
  useLauncherStatus: vi.fn(() => ({ data: { launcher: false, can_shutdown: false }, isLoading: false })),
  useShutdownApp: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))
