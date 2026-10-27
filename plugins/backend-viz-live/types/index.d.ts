export type Endpoint = {
  method: string
  path: string
  status: 'built' | 'missing' | 'undocumented'
  file: string | null
  line: number | null
}
export type Violation = { from: string; to: string; from_layer: string; to_layer: string }
export type Snapshot = {
  generated: string
  designed: number
  built: number
  missing: number
  undocumented: number
  violations: number
  untraced: number
  traces: number
  coverage: number | null
  endpoints: Endpoint[]
  violationList: Violation[]
  dashboard: string
}

declare module 'claude-code' {
  interface PluginState {
    'backend-viz-live': { snap: Snapshot | null }
  }
}
