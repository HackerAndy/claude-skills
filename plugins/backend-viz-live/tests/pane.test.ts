import { test, expect } from 'claude-code/testing'

const REPORT = JSON.stringify({
  generated: '2026-10-15T20:00:00',
  summary: { designed: 4, built: 3, missing: 1, undocumented: 1, violations: 1, coverage: 75 },
  endpoints: [
    { method: 'GET', path: '/orders', status: 'built', file: 'a.py', line: 1 },
    { method: 'DELETE', path: '/orders/{id}', status: 'missing', file: null, line: null },
    { method: 'POST', path: '/refund', status: 'undocumented', file: 'a.py', line: 9 },
  ],
  violations: [{ from: 'routes/a.py', to: 'repos/b.py', from_layer: 'routes', to_layer: 'repositories' }],
})

test('pane draws coverage, endpoints and violations from the report', async ($, on) => {
  on('session.root', () => ({ value: '/proj' }))
  on('fs.read', (_$: any, e: any) => {
    if (JSON.stringify(e).includes('report.json')) return { value: REPORT }
    throw new Error('ENOENT')
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.render', () => ({ value: null }))
  const out = await $.command.run({ command: 'backend-live', args: '', origin: 'user' } as any)
  expect(String((out as any).text)).toContain('opened')
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'backend-viz-live', surface, component: 'Pane', requestId: 'backend-viz', props: { title: 'Backend map', isFocused: false, bodyColumns: 80, placement: 'dock' } } as any)
    expect(await ui.find({ type: 'Text', text: /Contract 75%/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /\/refund/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /routes\/a\.py/ })).toBeDefined()
    await ui.unmount()
  }
})
