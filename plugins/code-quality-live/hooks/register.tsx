import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Band, Bands, Code, FileEntry, Finding, Fn, Help, Snapshot, View } from '../types'

const PANE = 'code-quality'
const TITLE = 'Code quality'
// Change the tag when the snapshot's fields change: it declines what an earlier version stored.
const snap = atom({ plugin: 'code-quality-live', key: 'snap' } as const, null as Snapshot | null, { shape: 'snap-2' })
const view = atom({ plugin: 'code-quality-live', key: 'view' } as const, {} as View)
// A project named with /quality-live <path>, looked at instead of the session's own.
const project = atom({ plugin: 'code-quality-live', key: 'project' } as const, '')
const WRITE_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
const COLOR = { green: 'success', yellow: 'warning', red: 'error' } as const
const LINT_COST = 5

const dir = (file: string) => (file.includes('/') ? file.slice(0, file.lastIndexOf('/')) : '.')
const base = (file: string) => file.slice(file.lastIndexOf('/') + 1)
const inFn = (f: Finding, fn: Fn) => f.line >= fn.line && f.line <= fn.end
const metricScore = (v: number, limit: number) => (v / limit <= 1 ? 100 - (10 * v) / limit : 90 - 30 * (v / limit - 1))

// Keeps what the pane draws from the report the code-quality gate writes (and each check refreshes).
function snapshot(r: any, page: string): Snapshot {
  const s = r.summary
  return {
    project: r.project,
    generated: r.generated,
    green: r.thresholds.green,
    yellow: r.thresholds.yellow,
    limits: r.limits,
    summary: { functions: s.functions, approved: s.approved, bands: s.bands, average: s.average, files: s.files, new: s.new },
    folders: r.folders,
    targets: r.targets.map((t: any) => ({ file: t.file, symbol: t.symbol, line: t.line, score: t.score, why: t.why, churn: t.churn })),
    files: r.files,
    rules: r.rules ?? {},
    metrics: r.metrics ?? {},
    page,
  }
}

// The session may be the project, or a folder inside it (ui/ of a monorepo): look up from there.
async function refresh($: any): Promise<Snapshot | null> {
  let d: string = (await read($, project)) || (await $.session.root())
  for (let i = 0; i < 5 && d; i++) {
    try {
      const next = snapshot(JSON.parse(await $.fs.read(`${d}/.quality/report.json`)), `${d}/.quality/report.html`)
      await update($, snap, () => next)
      const s = next.summary
      const share = s.functions ? Math.round((100 * s.approved) / s.functions) : 100
      $.ui.status(
        `Quality ${share}% approved` +
          (s.bands.red ? ` · ${s.bands.red} red` : '') +
          (s.bands.yellow ? ` · ${s.bands.yellow} yellow` : '') +
          (s.new ? ` · ${s.new} new ✗` : ''),
      )
      return next
    } catch {
      d = d.slice(0, d.lastIndexOf('/'))
    }
  }
  return null
}

/** Code lines worth showing in a narrow pane: each marked line with one line around it, gaps as null. */
function linesToShow(code: { start: number; lines: string[] }, marked: Set<number>, room: number): (number | null)[] {
  const keep = new Set<number>()
  for (const n of marked)
    for (const k of [n - 1, n, n + 1]) if (k >= code.start && k < code.start + code.lines.length) keep.add(k)
  const out: (number | null)[] = []
  let last = -1
  for (const n of [...keep].sort((a, b) => a - b)) {
    if (last >= 0 && n > last + 1) out.push(null)
    out.push(n)
    last = n
  }
  return out.slice(0, room)
}

type Span = { a: number; b: number | null; kind: 'branch' | 'lint' }

/** The line cut at its marks: [text, kind | null] pieces, columns 1-based, end exclusive. */
function pieces(text: string, spans: Span[]): [string, Span['kind'] | null][] {
  const cuts = new Set([0, text.length])
  for (const s of spans) {
    cuts.add(Math.max(0, s.a - 1))
    cuts.add(s.b == null ? text.length : Math.min(text.length, s.b - 1))
  }
  const pts = [...cuts].sort((x, y) => x - y)
  const out: [string, Span['kind'] | null][] = []
  for (let i = 0; i < pts.length - 1; i++) {
    const x = pts[i] ?? 0
    const y = pts[i + 1] ?? x
    if (x === y) continue
    const hit = spans.filter(s => s.a - 1 <= x && (s.b == null ? text.length : s.b - 1) >= y)
    out.push([text.slice(x, y), hit.some(s => s.kind === 'lint') ? 'lint' : hit.length ? 'branch' : null])
  }
  return out
}

/** Where a lint finding is on its lines; one spanning a whole function marks only its first line. */
function lintSpans(f: Finding): Map<number, Span[]> {
  const out = new Map<number, Span[]>()
  if ((f.end_line ?? f.line) - f.line >= 3) return out.set(f.line, [{ a: 1, b: 1, kind: 'lint' }])
  const last = f.end_line ?? f.line
  for (let n = f.line; n <= last; n++)
    out.set(n, [{ a: n === f.line ? (f.col ?? 1) : 1, b: n === last ? (f.end_col ?? null) : null, kind: 'lint' }])
  return out
}

/** Opens the report page in the browser: `open` on macOS, `xdg-open` elsewhere. */
async function openPage($: any, page: string) {
  for (const opener of ['open', 'xdg-open']) {
    try {
      if ((await $.process.run([opener, page])).exitCode === 0) return
    } catch {
      // not this platform's opener
    }
  }
  $.ui.toast(`Open ${page} in a browser`)
}

function helpFor(s: Snapshot, f: Finding): Help {
  return s.rules[f.rule] ?? s.metrics[f.rule] ?? { title: f.rule }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'quality-live',
      description: 'Open the live code-quality pane (scores, what to fix first, drill-down)',
      argumentHint: '[project path]',
    })
    const s = await refresh($)
    if (s) void $.ui.open({ id: PANE, title: TITLE })
    return next(e)
  })

  on('command.run', { command: 'quality-live' }, async ($, e) => {
    const path = e.args.trim().replace(/\/+$/, '')
    const full = path.startsWith('/') ? path : `${await $.session.root()}/${path}`
    if (path) await update($, project, () => full)
    const s = await refresh($)
    await update($, view, () => ({}))
    await $.ui.open({ id: PANE, title: TITLE })
    return {
      text: s
        ? 'Code quality pane opened.'
        : 'No .quality/report.json yet. Ask for the code-quality report (quality_gate.py report) first.',
    }
  })

  // The gate's PostToolUse hook rewrites the report after an edit; it can take a few seconds.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (WRITE_TOOLS.has(e.tool)) {
      void (async () => {
        for (const wait of [1500, 4000, 8000]) {
          await $.clock.sleep(wait)
          await refresh($)
        }
      })().catch(() => undefined)
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const s = await read($, snap)
    if (!s) return <Text dimColor>No code-quality report yet. Run quality_gate.py report, or ask for the code-quality report.</Text>
    const v = await read($, view)
    const cols = Math.max(30, e.viewport?.columns ?? 80)
    const room = Math.max(4, (e.viewport?.rows ?? 30) - 12)
    const band = (n: number | null): Band => (n == null || n >= s.green ? 'green' : n >= s.yellow ? 'yellow' : 'red')
    const go = (next: View) => () => void update($, view, () => next)

    const Score = ({ n }: { n: number | null }) => (
      <Text color={COLOR[band(n)]} bold>
        {(n == null ? '–' : `${n}%`).padStart(4)}
      </Text>
    )
    const Bar = ({ b, width }: { b: Bands; width: number }) => {
      const total = b.green + b.yellow + b.red || 1
      const part = (n: number) => (n ? Math.max(1, Math.round((width * n) / total)) : 0)
      const cells: Bands = { yellow: part(b.yellow), red: part(b.red), green: 0 }
      cells.green = Math.max(0, width - cells.yellow - cells.red)
      return (
        <Text>
          {(['green', 'yellow', 'red'] as const).map(k => (
            <Text color={COLOR[k]}>{'█'.repeat(cells[k])}</Text>
          ))}
        </Text>
      )
    }
    const CodeLines = ({ code, spans, room: max }: { code: { start: number; lines: string[] }; spans: Map<number, Span[]>; room: number }) => (
      <Box flexDirection="column">
        {linesToShow(code, new Set(spans.keys()), max).map(n => {
          if (n === null) return <Text dimColor>      ⋮</Text>
          const marks = spans.get(n) ?? []
          const lint = marks.some(m => m.kind === 'lint')
          const paths = marks.filter(m => m.kind === 'branch').length
          return (
            <Text wrap="truncate-end">
              <Text color={lint ? 'error' : undefined} dimColor={!lint}>
                {String(n).padStart(4)}
              </Text>
              <Text color="warning">{paths ? ` +${paths} ` : '    '}</Text>
              {pieces(code.lines[n - code.start] ?? '', marks).map(([t, kind]) =>
                kind === 'lint' ? (
                  <Text color="error" bold underline>
                    {t}
                  </Text>
                ) : kind === 'branch' ? (
                  <Text color="warning" bold>
                    {t}
                  </Text>
                ) : (
                  <Text>{t}</Text>
                ),
              )}
            </Text>
          )
        })}
      </Box>
    )
    const footer = (
      <Box flexDirection="column">
        <Text> </Text>
        <Button plain key="open" label="↗ Open the full report" onPress={() => void openPage($, s.page)} />
        <Text dimColor>updated {s.generated.replace('T', ' ')}</Text>
      </Box>
    )

    // One function: its score worked out, each issue in a line or two, and the lines that cause them.
    const entry: FileEntry | undefined = v.file ? s.files[v.file] : undefined
    const fn = v.fn && entry ? entry.functions.find(x => x.symbol === v.fn) : undefined
    if (v.file && entry && fn) {
      const own = entry.findings.filter(f => f.symbol === fn.symbol)
      const lint = entry.findings.filter(f => !f.symbol && inFn(f, fn))
      const branchy = own.some(f => f.rule === 'ccn' || f.rule === 'cognitive')
      const parts = Object.entries(fn.values).map(([m, val]) => ({ m, val, sc: metricScore(val, s.limits[m] ?? 1) }))
      const worst = parts.reduce((a, b) => (b.sc < a.sc ? b : a), parts[0] ?? { m: 'ccn', val: 0, sc: 100 })
      const spans = new Map<number, Span[]>()
      const code: Code | undefined = fn.code
      if (code && branchy)
        for (const [i, a, b] of code.branches)
          spans.set(code.start + i, [...(spans.get(code.start + i) ?? []), { a, b, kind: 'branch' }])
      for (const f of lint) for (const [n, sp] of lintSpans(f)) spans.set(n, [...(spans.get(n) ?? []), ...sp])
      return (
        <Box flexDirection="column">
          <Button plain dimColor key="back" label={`‹ ${base(v.file)}`} onPress={go({ folder: dir(v.file), file: v.file })} />
          <Text>
            <Score n={fn.score} /> <Text bold>{fn.symbol}</Text>{' '}
            <Text dimColor>
              :{fn.line}–{fn.end}
            </Text>
          </Text>
          <Text dimColor wrap="wrap">
            worst measure: {s.metrics[worst.m]?.title?.toLowerCase() ?? worst.m} {worst.val}/{s.limits[worst.m]} →{' '}
            {Math.round(worst.sc)}%{fn.smells ? `, −${LINT_COST} × ${fn.smells} lint` : ''} = {fn.score}%
          </Text>
          <Text> </Text>
          {own.map(f => (
            <Box flexDirection="column">
              <Text color="warning" wrap="wrap">
                ● {helpFor(s, f).title} <Text dimColor>({f.message})</Text>
              </Text>
              <Text dimColor wrap="wrap">
                {'  '}
                {helpFor(s, f).fix ?? helpFor(s, f).what}
              </Text>
            </Box>
          ))}
          {lint.map(f => (
            <Box flexDirection="column">
              <Text color="error" wrap="wrap">
                ● {f.new ? 'NEW ' : ''}
                {f.message.replace(/\.$/, '')}{' '}
                <Text dimColor>
                  line {f.line} · {f.rule.split(':').pop()}
                </Text>
              </Text>
              {helpFor(s, f).what && (
                <Text dimColor wrap="wrap">
                  {'  '}
                  {helpFor(s, f).what}
                </Text>
              )}
            </Box>
          ))}
          {own.length === 0 && lint.length === 0 && <Text color="success">Inside every limit.</Text>}
          <Text> </Text>
          {code && spans.size > 0 && (
            <Text dimColor>
              {branchy ? '+n: paths the line adds (yellow)' : ''}
              {branchy && lint.length ? ' · ' : ''}
              {lint.length ? 'lint (red)' : ''}
            </Text>
          )}
          {code ? (
            <CodeLines code={code} spans={spans} room={Math.max(6, room - own.length * 2 - lint.length * 2)} />
          ) : (
            lint.map(f => (f.context ? <CodeLines code={f.context} spans={lintSpans(f)} room={5} /> : <Text> </Text>))
          )}
          {footer}
        </Box>
      )
    }

    if (v.file && entry) {
      const fns = [...entry.functions].sort((a, b) => a.score - b.score || a.line - b.line)
      const low = fns.filter(x => x.score < s.green || entry.findings.some(f => f.new && inFn(f, x)))
      const loose = entry.findings.filter(f => f.symbol === '<file>' || (!f.symbol && !entry.functions.some(x => inFn(f, x))))
      const fresh = entry.findings.filter(f => f.new).length
      return (
        <Box flexDirection="column">
          <Button plain dimColor key="back" label={`‹ ${dir(v.file)}/`} onPress={go({ folder: dir(v.file) })} />
          <Text bold wrap="truncate-end">
            {v.file}
          </Text>
          <Text dimColor>
            {fns.filter(x => x.score >= s.green).length}/{fns.length} functions approved · {entry.findings.length} findings
            {fresh ? ` · ${fresh} new` : ''}
          </Text>
          <Text> </Text>
          {low.slice(0, room).map(x => (
            <Button plain key={`f:${x.symbol}`} onPress={go({ folder: dir(v.file ?? ''), file: v.file, fn: x.symbol })}>
              <Score n={x.score} /> {x.symbol}{' '}
              <Text dimColor>
                :{x.line} · {x.why.join(' · ')}
              </Text>
            </Button>
          ))}
          {low.length === 0 && <Text color="success">Every function is at {s.green}% or more.</Text>}
          {fns.length > low.length && <Text dimColor>+{fns.length - low.length} approved</Text>}
          {loose.slice(0, 3).map(f => (
            <Box flexDirection="column">
              <Text> </Text>
              <Text color="error" wrap="wrap">
                ● {f.new ? 'NEW ' : ''}
                {f.message.replace(/\.$/, '')} <Text dimColor>line {f.line}</Text>
              </Text>
              {helpFor(s, f).what && (
                <Text dimColor wrap="wrap">
                  {'  '}
                  {helpFor(s, f).what}
                </Text>
              )}
              {f.context && <CodeLines code={f.context} spans={lintSpans(f)} room={5} />}
            </Box>
          ))}
          {footer}
        </Box>
      )
    }

    if (v.folder) {
      const names = Object.entries(s.files)
        .filter(([n]) => dir(n) === v.folder)
        .map(([n, f]) => ({ n, f, worst: Math.min(101, ...f.functions.map(x => x.score)) }))
        .sort((a, b) => a.worst - b.worst || a.n.localeCompare(b.n))
      return (
        <Box flexDirection="column">
          <Button plain dimColor key="back" label="‹ All folders" onPress={go({})} />
          <Text bold wrap="truncate-end">
            {v.folder}/
          </Text>
          <Text> </Text>
          {names.slice(0, room).map(({ n, f, worst }) => (
            <Button plain key={n} onPress={go({ folder: v.folder, file: n })}>
              <Score n={worst === 101 ? null : worst} /> {base(n)}{' '}
              <Text dimColor>
                {f.functions.filter(x => x.score >= s.green).length}/{f.functions.length}
                {f.findings.some(x => x.new) ? ` · ${f.findings.filter(x => x.new).length} new` : ''}
              </Text>
            </Button>
          ))}
          {names.length > room && <Text dimColor>…{names.length - room} more</Text>}
          {footer}
        </Box>
      )
    }

    const sum = s.summary
    const share = sum.functions ? Math.round((100 * sum.approved) / sum.functions) : 100
    const flagged = s.folders.filter(f => f.bands.yellow || f.bands.red || f.new)
    const half = Math.max(2, Math.floor(room / 2))
    return (
      <Box flexDirection="column">
        <Text>
          <Text bold color={COLOR[band(share)]}>
            {share}% approved
          </Text>{' '}
          <Text dimColor>
            {sum.approved}/{sum.functions} functions · avg {sum.average ?? '–'}% · {s.project}
          </Text>
        </Text>
        <Bar b={sum.bands} width={Math.min(48, cols - 2)} />
        <Text>
          <Text color="success">■ {sum.bands.green}</Text> <Text dimColor>{s.green}%+</Text>
          {'  '}
          <Text color="warning">■ {sum.bands.yellow}</Text>{' '}
          <Text dimColor>
            {s.yellow}–{s.green - 1}%
          </Text>
          {'  '}
          <Text color="error">■ {sum.bands.red}</Text> <Text dimColor>below {s.yellow}%</Text>
        </Text>
        <Text color={sum.new ? 'error' : 'success'}>
          {sum.new ? `✗ ${sum.new} new findings since the baseline` : '✓ gate clean'}
        </Text>
        <Text> </Text>
        <Text bold>Fix first</Text>
        {s.targets.length === 0 && <Text color="success">Nothing below {s.green}%.</Text>}
        {s.targets.slice(0, half).map(t => (
          <Button plain key={`t:${t.file}:${t.symbol}`} onPress={go({ folder: dir(t.file), file: t.file, fn: t.symbol })}>
            <Score n={t.score} /> {t.symbol}{' '}
            <Text dimColor>
              {base(t.file)}:{t.line} · {t.why.join(' · ')}
            </Text>
          </Button>
        ))}
        <Text> </Text>
        <Text bold>
          Folders <Text dimColor>worst first</Text>
        </Text>
        {flagged.slice(0, half).map(f => (
          <Button plain key={`d:${f.path}`} onPress={go({ folder: f.path })}>
            <Score n={f.worst} /> {f.path}/{' '}
            <Text dimColor>
              {f.approved}/{f.functions}
              {f.new ? ` · ${f.new} new` : ''}
            </Text>
          </Button>
        ))}
        {flagged.length > half && (
          <Text dimColor>
            …{flagged.length - half} more below {s.green}%
          </Text>
        )}
        <Text dimColor>{s.folders.length - flagged.length} folders all green</Text>
        {footer}
      </Box>
    )
  })
}
