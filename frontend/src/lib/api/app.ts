import apiClient from './client'

export interface LauncherStatus {
  launcher: boolean
  can_shutdown: boolean
}

export interface ErrorLogResponse {
  path: string
  count: number
  records: string[]
}

export const appApi = {
  errors: async (lines = 200, level?: 'warning' | 'error' | 'critical') => {
    const response = await apiClient.get<ErrorLogResponse>('/app/errors', { params: { lines, level } })
    return response.data
  },
  clearErrors: async () => {
    await apiClient.delete('/app/errors')
  },
  launcherStatus: async () => {
    const response = await apiClient.get<LauncherStatus>('/app/launcher')
    return response.data
  },
  shutdown: async () => {
    await apiClient.post('/app/shutdown')
  },
}
