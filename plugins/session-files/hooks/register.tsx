import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { GitMark, Outside, Snapshot, ViewMode } from '../types'

const PANE = 'session-files'
const TITLE = 'Files'
const MAX_ROWS = 3000
const POLL_MS = 4000
const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])

const EMPTY: Snapshot = { root: '', isGit: false, files: [], git: {} }
const snapshot = atom({ plugin: 'session-files', key: 'snapshot' } as const, EMPTY)
const touched = atom({ plugin: 'session-files', key: 'touched' } as const, [] as string[])
const elsewhere = atom({ plugin: 'session-files', key: 'elsewhere' } as const, [] as Outside[])
const collapsed = atom({ plugin: 'session-files', key: 'collapsed' } as const, [] as string[])
const mode = atom({ plugin: 'session-files', key: 'mode' } as const, 'all' as ViewMode)

let isRefreshing = false

function markOf(xy: string): GitMark {
  if (xy === '??') return '?'
  if (xy.includes('U') || xy === 'AA' || xy === 'DD') return 'U'
  if (xy.includes('D')) return 'D'
  if (xy.includes('R')) return 'R'
  if (xy.includes('A')) return 'A'
  return 'M'
}

function parseStatus(out: string): Record<string, GitMark> {
  const git: Record<string, GitMark> = {}
  const parts = out.split('\0')
  for (let i = 0; i < parts.length; i++) {
    const entry = parts[i] ?? ''
    if (entry.length < 4) continue
    const xy = entry.slice(0, 2)
    git[entry.slice(3)] = markOf(xy)
    // A rename or copy is followed by its original path.
    if (xy[0] === 'R' || xy[0] === 'C') i++
  }
  return git
}

async function scan($: EngineInterface): Promise<Snapshot> {
  const cwd = await $.session.cwd()
  const top = await $.process.run(['git', 'rev-parse', '--show-toplevel'])
  if (top.exitCode === 0) {
    const root = top.stdout.trim()
    const [listed, status] = await Promise.all([
      $.process.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'], { cwd: root }),
      $.process.run(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], {
        cwd: root,
      }),
    ])
    const files = listed.stdout.split('\0').filter(Boolean)
    return { root, isGit: true, files, git: parseStatus(status.stdout) }
  }
  const found = await $.process.run([
    'find', '.', '-type', 'f',
    '-not', '-path', '*/.*', '-not', '-path', '*/node_modules/*',
  ])
  const files = found.stdout
    .split('\n')
    .filter(Boolean)
    .map(p => p.replace(/^\.\//, ''))
    .slice(0, 20000)
  return { root: cwd, isGit: false, files, git: {} }
}

async function refresh($: EngineInterface) {
  if (isRefreshing) return
  isRefreshing = true
  try {
    const next = await scan($)
    await update($, snapshot, prev =>
      JSON.stringify(prev) === JSON.stringify(next) ? prev : next,
    )
  } finally {
    isRefreshing = false
  }
}

// Windows reports paths with backslashes and git with slashes; compare them on slashes (and, on a drive, ignoring case).
const norm = (p: string) => p.replace(/\\/g, '/')
const isDrivePath = (p: string) => /^[A-Za-z]:\//.test(p)

function relativeTo(root: string, path: string): string | undefined {
  if (!root) return undefined
  const base = norm(root).replace(/\/+$/, '') + '/'
  const p = norm(path)
  const inside = isDrivePath(base) ? p.toLowerCase().startsWith(base.toLowerCase()) : p.startsWith(base)
  if (inside) return p.slice(base.length)
  if (!p.startsWith('/') && !isDrivePath(p)) return p // already relative to the project
  return undefined
}

const labels = new Map<string, string>()

// A short name for a file outside the project, so the pane shows "Temp" or ".claude" instead of a long path: the
// settings folder, else the name of the git repository the file lives in, else a temp folder, else its parent folder.
async function labelFor($: EngineInterface, path: string): Promise<string> {
  const segs = norm(path).split('/').filter(Boolean)
  const dirs = segs.slice(0, -1)
  const lower = dirs.map(s => s.toLowerCase())
  if (lower.includes('.claude')) return '.claude'
  const dir = norm(path).replace(/\/[^/]*$/, '')
  const cached = labels.get(dir)
  if (cached) return cached
  let label = ''
  try {
    const top = await $.process.run(['git', 'rev-parse', '--show-toplevel'], { cwd: dir })
    if (top.exitCode === 0) label = top.stdout.trim().split('/').pop() ?? ''
  } catch {
    // the folder may be gone; fall through to the name-based guesses
  }
  if (!label) {
    const temp = lower.findIndex(s => s === 'temp' || s === 'tmp')
    label = temp >= 0 ? dirs[temp]! : (dirs[dirs.length - 1] ?? 'other')
  }
  labels.set(dir, label)
  return label
}

type Dir = { dirs: Map<string, Dir>; files: string[] }

function buildTree(paths: string[]): Dir {
  const top: Dir = { dirs: new Map(), files: [] }
  for (const path of paths) {
    const segs = path.split('/')
    let at = top
    for (const seg of segs.slice(0, -1)) {
      let child = at.dirs.get(seg)
      if (!child) {
        child = { dirs: new Map(), files: [] }
        at.dirs.set(seg, child)
      }
      at = child
    }
    at.files.push(segs[segs.length - 1] ?? path)
  }
  return top
}

type Row =
  | { kind: 'dir'; path: string; name: string; depth: number; isOpen: boolean; isHot: boolean; isTouched: boolean }
  | { kind: 'file'; path: string; name: string; depth: number; mark?: GitMark; isTouched: boolean }

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'files',
      description: 'Show the file tree, with files changed this session highlighted',
    })
    void refresh($)
    $.clock.every(POLL_MS, () => void refresh($))
    void $.ui.open({ id: PANE, title: TITLE })

    return next(e)
  })

  on('command.run', { command: 'files' }, async $ => {
    await refresh($)
    await $.ui.open({ id: PANE, title: TITLE })

    return { text: 'Files pane opened.' }
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const tool = String(e.tool)
    const answered = ran as { deny?: string; isError?: boolean }
    if (EDIT_TOOLS.has(tool) && !answered.deny && !answered.isError) {
      const args = e as unknown as { file_path?: string; notebook_path?: string }
      const path = args.file_path ?? args.notebook_path
      let { root } = await read($, snapshot)
      if (!root) {
        await refresh($)
        root = (await read($, snapshot)).root
      }
      const rel = path ? relativeTo(root, path) : undefined
      if (rel) {
        await update($, touched, list => (list.includes(rel) ? list : [...list, rel]))
      } else if (path) {
        const full = norm(path)
        const label = await labelFor($, full)
        const name = full.split('/').pop() ?? full
        await update($, elsewhere, list => (list.some(x => x.path === full) ? list : [...list, { path: full, label, name }]))
      }
    }
    if (EDIT_TOOLS.has(tool) || tool === 'Bash') void refresh($)

    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const snap = await read($, snapshot)
    const edited = await read($, touched)
    const outside = await read($, elsewhere)
    const shut = new Set(await read($, collapsed))
    const view = await read($, mode)

    const editedSet = new Set(edited)
    const isChanged = (p: string) => editedSet.has(p) || p in snap.git
    const all = new Set(snap.files)
    for (const p of Object.keys(snap.git)) all.add(p)
    for (const p of edited) all.add(p)
    const shown = [...all].filter(p => view === 'all' || isChanged(p))

    const hot = new Set<string>()
    const hotTouched = new Set<string>()
    for (const p of all) {
      if (!isChanged(p)) continue
      const segs = p.split('/')
      for (let i = 1; i < segs.length; i++) {
        const dir = segs.slice(0, i).join('/')
        hot.add(dir)
        if (editedSet.has(p)) hotTouched.add(dir)
      }
    }

    const rows: Row[] = []
    const walk = (dir: Dir, prefix: string, depth: number) => {
      for (const name of [...dir.dirs.keys()].sort()) {
        if (rows.length >= MAX_ROWS) return
        const path = prefix + name
        const isOpen = !shut.has(path)
        rows.push({ kind: 'dir', path, name, depth, isOpen, isHot: hot.has(path), isTouched: hotTouched.has(path) })
        if (isOpen) walk(dir.dirs.get(name)!, path + '/', depth + 1)
      }
      for (const name of dir.files.sort()) {
        if (rows.length >= MAX_ROWS) return
        const path = prefix + name
        rows.push({ kind: 'file', path, name, depth, mark: snap.git[path], isTouched: editedSet.has(path) })
      }
    }
    walk(buildTree(shown), '', 0)

    const changedCount = [...all].filter(isChanged).length
    // files edited outside the project, grouped under a short label; a duplicate name gets its parent folder
    const groups = new Map<string, Outside[]>()
    for (const o of outside) groups.set(o.label, [...(groups.get(o.label) ?? []), o])
    const shortName = (o: Outside, peers: Outside[]) =>
      peers.filter(x => x.name === o.name).length > 1 ? o.path.split('/').slice(-2).join('/') : o.name
    const toggleMode = () => update($, mode, m => (m === 'all' ? 'changed' : 'all'))
    const toggleDir = (path: string) =>
      update($, collapsed, list =>
        list.includes(path) ? list.filter(p => p !== path) : [...list, path],
      )

    const markColor = (mark?: GitMark) =>
      mark === 'D' || mark === 'U' ? 'error'
        : mark === '?' || mark === 'A' ? 'success'
        : mark === 'R' ? 'suggestion'
        : mark === 'M' ? 'warning'
        : undefined
    // Untracked shows as U (new), so a merge conflict gets ! to stay distinct.
    const badgeOf = (mark?: GitMark) => (mark === '?' ? 'U' : mark === 'U' ? '!' : mark)

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          <Text bold>{norm(snap.root).split('/').pop() || 'files'}</Text>
          <Text dimColor>
            {edited.length + outside.length} edited by Claude · {changedCount} changed
          </Text>
        </Box>
        <Box flexDirection="row" gap={1}>
          <Button key="mode" hotkey="v" onPress={toggleMode}>
            {view === 'all' ? 'Show changed only' : 'Show all files'}
          </Button>
          <Button key="refresh" hotkey="r" onPress={() => refresh($)}>Refresh</Button>
        </Box>
        <Text dimColor>
          <Text color="claude">● edited this session</Text>  <Text color="warning">M</Text> modified{' '}
          <Text color="success">U</Text> new  <Text color="success">A</Text> added{' '}
          <Text color="suggestion">R</Text> renamed  <Text color="error">D</Text> deleted{' '}
          <Text color="error">!</Text> conflict
        </Text>
        {!snap.isGit && snap.root && <Text dimColor>Not a git repo: showing session edits only.</Text>}
        {rows.length === 0 && (
          <Text dimColor>{view === 'changed' ? 'No changed files yet.' : 'Scanning…'}</Text>
        )}
        {rows.map(row => {
          const indent = '  '.repeat(row.depth)
          if (row.kind === 'dir') {
            return (
              <Box key={'r:' + row.path} flexDirection="row">
                {indent && <Text>{indent}</Text>}
                <Button
                  key={'d:' + row.path}
                  plain
                  label={`${row.isOpen ? '▾' : '▸'} ${row.name}/`}
                  onPress={() => toggleDir(row.path)}
                />
                {row.isHot && <Text color={row.isTouched ? 'claude' : 'warning'}> •</Text>}
              </Box>
            )
          }
          const color = row.isTouched ? 'claude' : markColor(row.mark)
          const badge = badgeOf(row.mark)
          return (
            <Box key={'f:' + row.path} flexDirection="row">
              <Text
                color={color}
                bold={row.isTouched}
                strikethrough={row.mark === 'D'}
                dimColor={!color}
                wrap="truncate-end"
              >
                {indent}  {row.name}
              </Text>
              {row.isTouched && <Text color="claude"> ●</Text>}
              {badge && <Text color={markColor(row.mark)}> {badge}</Text>}
            </Box>
          )
        })}
        {rows.length >= MAX_ROWS && (
          <Text dimColor>Showing the first {MAX_ROWS} rows. Collapse folders or show changed only.</Text>
        )}
        {groups.size > 0 && <Text dimColor>Edited outside this project</Text>}
        {[...groups].map(([label, list]) => (
          <Box key={'g:' + label} flexDirection="column">
            <Box flexDirection="row" gap={1}>
              <Text bold>{label}/</Text>
              <Text dimColor>{list.length}</Text>
            </Box>
            {list.map(o => (
              <Box key={'o:' + o.path} flexDirection="row">
                <Text color="claude" bold wrap="truncate-end">
                  {'  '}
                  {shortName(o, list)}
                </Text>
                <Text color="claude"> ●</Text>
              </Box>
            ))}
          </Box>
        ))}
      </Box>
    )
  })
}
