import apiClient from './client'

export interface LauncherStatus {
  launcher: boolean
  can_shutdown: boolean
}

export const appApi = {
  launcherStatus: async () => {
    const response = await apiClient.get<LauncherStatus>('/app/launcher')
    return response.data
  },
  shutdown: async () => {
    await apiClient.post('/app/shutdown')
  },
}
