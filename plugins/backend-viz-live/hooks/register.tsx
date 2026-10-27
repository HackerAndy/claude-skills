import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Snapshot } from '../types'

const PANE = 'backend-viz'
const snap = atom({ plugin: 'backend-viz-live', key: 'snap' } as const, null as Snapshot | null)
const WRITE_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])

// Reads the report the backend-viz PostToolUse hook writes after every edit.
async function refresh($: any): Promise<Snapshot | null> {
  const top: string = await $.session.root()
  let r: any
  let root = top
  // the session may be the project itself or a monorepo holding it (e.g. backend/)
  for (const dir of [top, `${top}/backend`]) {
    try {
      r = JSON.parse(await $.fs.read(`${dir}/.backend-viz/report.json`))
      root = dir
      break
    } catch {
      // not here
    }
  }
  if (!r) return null // project not opted in (no design/ folder) or no report yet
  const s = r.summary
  const next: Snapshot = {
    generated: r.generated,
    designed: s.designed, built: s.built, missing: s.missing,
    undocumented: s.undocumented, violations: s.violations, coverage: s.coverage,
    untraced: s.untraced ?? 0, traces: s.traces ?? 0,
    endpoints: r.endpoints, violationList: r.violations,
    dashboard: `${root}/.backend-viz/dashboard.html`,
  }
  await update($, snap, () => next)
  $.ui.status(
    `API ${s.coverage ?? '–'}% · ${s.missing} todo` +
      (s.undocumented ? ` · ${s.undocumented} off-contract` : '') +
      (s.violations ? ` · ${s.violations} layer ✗` : '') +
      (s.untraced ? ` · ${s.untraced} untraced` : ''),
  )
  return next
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'backend-live',
      description: 'Open the live backend map pane (contract coverage + layer drift)',
    })
    const s = await refresh($)
    if (s) void $.ui.open({ id: PANE, title: 'Backend map' })
    return next(e)
  })

  on('command.run', { command: 'backend-live' }, async $ => {
    const s = await refresh($)
    await $.ui.open({ id: PANE, title: 'Backend map' })
    return {
      text: s
        ? 'Backend map pane opened.'
        : 'No .backend-viz/report.json yet. Run /backend-viz map first.',
    }
  })

  // After any file edit, re-read the report the backend-viz PostToolUse hook rewrites.
  // (tool.call rather than classic.PostToolUse so it also runs where an org manages Claude Code;
  // a second read a moment later catches the hook finishing after the tool.)
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (WRITE_TOOLS.has(e.tool)) {
      void (async () => {
        await refresh($)
        await $.clock.sleep(1500)
        await refresh($)
      })().catch(() => undefined)
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link } = $.ui.resolve(e)
    const s = await read($, snap)
    if (!s) return <Text dimColor>No backend report yet. Run /backend-viz map.</Text>

    const room = Math.max(4, (e.viewport?.rows ?? 30) - 8)
    const order = { undocumented: 0, missing: 1, built: 2 } as const
    const eps = [...s.endpoints].sort((a, b) => order[a.status] - order[b.status])
    const mark = { built: '●', missing: '○', undocumented: '◆' } as const
    const color = { built: 'success', missing: 'warning', undocumented: 'merged' } as const

    return (
      <Box flexDirection="column">
        <Text bold>
          Contract {s.coverage ?? '–'}% · {s.built}/{s.designed} built
        </Text>
        <Text dimColor>
          ○ {s.missing} to build · ◆ {s.undocumented} off-contract ·{' '}
          {s.violations ? `✗ ${s.violations} layer violations` : 'layers clean'} ·{' '}
          {s.untraced ? `${s.untraced} untraced` : 'all traced'} · {s.traces} traces
        </Text>
        <Text> </Text>
        {eps.slice(0, room).map(ep => (
          <Text color={color[ep.status]}>
            {mark[ep.status]} {ep.method.padEnd(6)} {ep.path}
          </Text>
        ))}
        {eps.length > room && <Text dimColor>…{eps.length - room} more</Text>}
        {s.violationList.slice(0, 5).map(v => (
          <Text color="error">
            ✗ {v.from} → {v.to} ({v.from_layer}→{v.to_layer})
          </Text>
        ))}
        <Text> </Text>
        <Link href={`file://${s.dashboard}`} label="Open full visual dashboard" />
        <Text dimColor>updated {s.generated.replace('T', ' ')}</Text>
      </Box>
    )
  })
}
