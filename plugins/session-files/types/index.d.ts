export type GitMark = 'M' | 'A' | 'D' | 'R' | 'U' | '?'

export type Snapshot = {
  root: string
  isGit: boolean
  files: string[]
  git: Record<string, GitMark>
}

export type ViewMode = 'all' | 'changed'

/** A file Claude edited outside the project: its slash-separated path, the short label it is grouped under, its file name. */
export type Outside = { path: string; label: string; name: string }

declare module 'claude-code' {
  interface PluginState {
    'session-files': {
      snapshot: Snapshot
      touched: string[]
      elsewhere: Outside[]
      collapsed: string[]
      mode: ViewMode
    }
  }
}
