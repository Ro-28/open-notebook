import apiClient from './client'

export interface LearningSession {
  id: string
  notebook_id: string
  title: string
  requirement: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  step?: string | null
  progress?: number | null
  message?: string | null
  error?: string | null
  job_id?: string | null
  classroom_id?: string | null
  classroom_url?: string | null
  options?: Record<string, unknown> | null
  material_stats?: {
    sources?: number
    insights?: number
    notes?: number
    chars?: number
    truncated?: boolean
  } | null
  created?: string | null
  updated?: string | null
}

export interface LearningSessionCreate {
  requirement?: string
  title?: string
  include_sources?: boolean
  include_insights?: boolean
  include_notes?: boolean
  enable_tts?: boolean
  enable_image_generation?: boolean
  enable_web_search?: boolean
}

export interface LearningStatus {
  available: boolean
  url: string
  public_url: string
  status_code?: number | null
  error?: string | null
}

export const learnApi = {
  status: async () => {
    const response = await apiClient.get<LearningStatus>('/learn/status')
    return response.data
  },

  list: async (notebookId: string) => {
    const response = await apiClient.get<LearningSession[]>(`/notebooks/${notebookId}/learn`)
    return response.data
  },

  create: async (notebookId: string, data: LearningSessionCreate) => {
    const response = await apiClient.post<LearningSession>(`/notebooks/${notebookId}/learn`, data)
    return response.data
  },

  get: async (sessionId: string) => {
    const response = await apiClient.get<LearningSession>(`/learn/${sessionId}`)
    return response.data
  },

  delete: async (sessionId: string) => {
    await apiClient.delete(`/learn/${sessionId}`)
  },
}
