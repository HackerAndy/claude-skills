export type GitMark = 'M' | 'A' | 'D' | 'R' | 'U' | '?'

export type Snapshot = {
  root: string
  isGit: boolean
  files: string[]
  git: Record<string, GitMark>
}

export type ViewMode = 'all' | 'changed'

declare module 'claude-code' {
  interface PluginState {
    'session-files': {
      snapshot: Snapshot
      touched: string[]
      collapsed: string[]
      mode: ViewMode
    }
  }
}
