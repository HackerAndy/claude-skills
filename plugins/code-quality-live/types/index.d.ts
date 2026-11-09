export type Band = 'green' | 'yellow' | 'red'
export type Bands = Record<Band, number>
/** A function's code as the report keeps it: lines from `start`, decision points as [line index, col, end col, kind]. */
export type Code = { start: number; lines: string[]; more: number; branches: [number, number, number, string][]; nested?: [number, number][] }
export type Fn = {
  symbol: string
  line: number
  end: number
  score: number
  why: string[]
  values: Record<string, number>
  smells: number
  code?: Code
}
export type Finding = {
  line: number
  rule: string
  message: string
  symbol: string | null
  new: boolean
  col?: number
  end_line?: number
  end_col?: number
  context?: { start: number; lines: string[] }
}
export type FileEntry = { functions: Fn[]; findings: Finding[] }
export type Help = { title?: string; what?: string; why?: string; fix?: string; url?: string }
export type Folder = {
  path: string
  files: number
  functions: number
  approved: number
  bands: Bands
  worst: number | null
  findings: number
  new: number
}
export type Target = { file: string; symbol: string; line: number; score: number; why: string[]; churn: number }
export type Snapshot = {
  project: string
  generated: string
  green: number
  yellow: number
  limits: Record<string, number>
  summary: { functions: number; approved: number; bands: Bands; average: number | null; files: number; new: number }
  folders: Folder[]
  targets: Target[]
  files: Record<string, FileEntry>
  rules: Record<string, Help>
  metrics: Record<string, Help>
  page: string
}
/** Where the pane is: the overview, a folder's files, a file's functions, or one function. */
export type View = { folder?: string; file?: string; fn?: string }

declare module 'claude-code' {
  interface PluginState {
    'code-quality-live': { snap: Shaped<Snapshot | null>; view: View; project: string }
  }
}
