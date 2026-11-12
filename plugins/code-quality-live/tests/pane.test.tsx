import { expect, test } from 'claude-code/testing'

const fn = (symbol: string, line: number, score: number, why: string[] = [], extra: object = {}) => ({
  symbol, line, end: line + 9, score, values: { ccn: 3, cognitive: 2, nloc: 9, params: 1 }, smells: 0, why, ...extra,
})
const CODE = {
  start: 4,
  lines: ['def legacy_price(order, cache={}):', '    if order and order.rush:', '        return 1', '    return 2'],
  more: 0,
  branches: [[1, 5, 7, 'branch'], [1, 14, 17, 'branch']],
}
const REPORT = JSON.stringify({
  version: 1,
  generated: '2026-11-08T19:00:00',
  project: 'shop',
  thresholds: { green: 90, yellow: 70 },
  limits: { ccn: 10, cognitive: 15, nloc: 60, params: 5, file_nloc: 500 },
  summary: { functions: 4, approved: 2, bands: { green: 2, yellow: 1, red: 1 }, average: 80, files: 2, new: 1 },
  folders: [
    { path: 'app', files: 1, functions: 3, approved: 1, bands: { green: 1, yellow: 1, red: 1 }, worst: 41, findings: 3, new: 1 },
    { path: 'web', files: 1, functions: 1, approved: 1, bands: { green: 1, yellow: 0, red: 0 }, worst: 96, findings: 0, new: 0 },
  ],
  targets: [{ file: 'app/orders.py', ...fn('legacy_price', 4, 41, ['cognitive complexity 30 > 15']), churn: 3, priority: 236 }],
  files: {
    'app/orders.py': {
      functions: [
        fn('legacy_price', 4, 41, ['cognitive complexity 30 > 15'], { values: { ccn: 9, cognitive: 30, nloc: 9, params: 2 }, smells: 1, costs: { cognitive: 0.81 }, code: CODE }),
        fn('shipping', 30, 81, ['1 lint finding(s)']),
        fn('subtotal', 50, 98),
      ],
      findings: [
        { line: 4, rule: 'cognitive', message: 'cognitive complexity 30 > 15', symbol: 'legacy_price', new: false },
        { line: 4, rule: 'ruff:B006', message: 'Do not use mutable data structures for argument defaults', symbol: null, new: true, col: 31, end_line: 4, end_col: 33 },
        { line: 1, rule: 'file_nloc', message: 'file has 600 lines of code > 500; split the module', symbol: '<file>', new: false },
      ],
    },
    'web/cart.ts': { functions: [fn('total', 1, 96)], findings: [] },
  },
  rules: { 'ruff:B006': { title: 'Do not use mutable data structures for argument defaults', what: 'Checks for uses of mutable objects as function argument defaults.' } },
  metrics: {
    cognitive: { title: 'Hard to follow', fix: 'Flatten it: handle the special cases first and return.' },
    file_nloc: { title: 'File too long', what: 'The file has more lines of code than the limit.' },
  },
})

const PANE = {
  plugin: 'code-quality-live',
  component: 'Pane',
  requestId: 'code-quality',
  props: { title: 'Code quality', isFocused: true, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

function engine(on: any, statuses: string[]) {
  on('session.root', () => ({ value: '/proj/app' }))
  on('fs.read', (_$: any, e: any) => {
    if (JSON.stringify(e).includes('/proj/.quality/report.json')) return { value: REPORT }
    throw new Error('ENOENT')
  })
  on('command.register', () => ({ value: { command: 'quality-live' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', (_$: any, e: any) => {
    statuses.push(JSON.stringify(e))
    return { value: undefined }
  })
}

test('the pane shows the share approved, what to fix first, and drills into a folder and a file', async ($, on) => {
  const statuses: string[] = []
  engine(on, statuses)
  const out = await $.command.run({ command: 'quality-live', args: '', origin: 'user' } as any)
  expect(String((out as any).text)).toContain('opened')
  expect(statuses.join()).toContain('Quality 50% approved · 1 red · 1 yellow · 1 new')

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface } as any)
    expect(await ui.find({ type: 'Text', text: /50% approved/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1 new findings since the baseline/ })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: /legacy_price/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1 folders all green/ })).toBeDefined()

    await ui.press({ key: 'd:app' })
    expect(await ui.find({ type: 'Button', text: /orders\.py/ })).toBeDefined()
    await ui.press({ key: 'app/orders.py' })
    expect(await ui.find({ type: 'Button', text: /shipping/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /\+1 approved/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /split the module/ })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.press({ key: 'back' })
    expect(await ui.find({ type: 'Text', text: /Fix first/ })).toBeDefined()

    // A function: its score worked out, the issues in plain words, the lines that cause them marked.
    await ui.press({ key: 't:app/orders.py:legacy_price' })
    expect(await ui.find({ type: 'Text', text: /costs: hard to follow −0.81 = 41%/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Flatten it/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /mutable objects as function argument defaults/ })).toBeDefined()
    expect((await ui.find({ type: 'Text', text: /^ \+2 $/ }))?.text).toBe(' +2 ')
    expect((await ui.find({ type: 'Text', text: /^and$/ }))?.text).toBe('and')
    expect((await ui.find({ type: 'Text', text: /^\{\}$/ }))?.text).toBe('{}')
    await ui.press({ key: 'back' })
    expect(await ui.find({ type: 'Button', text: /legacy_price/ })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('without a report the pane says how to make one', async ($, on) => {
  on('session.root', () => ({ value: '/elsewhere' }))
  on('fs.read', () => {
    throw new Error('ENOENT')
  })
  on('command.register', () => ({ value: { command: 'quality-live' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const out = await $.command.run({ command: 'quality-live', args: '', origin: 'user' } as any)
  expect(String((out as any).text)).toContain('No .quality/report.json')
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' } as any)
  expect(await ui.find({ type: 'Text', text: /No code-quality report yet/ })).toBeDefined()
  await ui.unmount()
})

test('/quality-live <path> looks at another project', async ($, on) => {
  const statuses: string[] = []
  on('session.root', () => ({ value: '/elsewhere' }))
  on('fs.read', (_$: any, e: any) => {
    if (JSON.stringify(e).includes('/proj/.quality/report.json')) return { value: REPORT }
    throw new Error('ENOENT')
  })
  on('command.register', () => ({ value: { command: 'quality-live' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', (_$: any, e: any) => {
    statuses.push(JSON.stringify(e))
    return { value: undefined }
  })
  const out = await $.command.run({ command: 'quality-live', args: '/proj/', origin: 'user' } as any)
  expect(String((out as any).text)).toContain('opened')
  expect(statuses.join()).toContain('Quality 50% approved')
})
