import { expect, test } from 'claude-code/testing'

const STATUS = [' M src/app.ts', '?? notes.md', ' D old.txt', 'UU merge.ts', ''].join('\0')
const FILES = ['src/app.ts', 'src/util.ts', 'notes.md', 'old.txt', 'merge.ts', 'README.md', ''].join('\0')

test('marks Claude edits and git changes in the pane', async ($, on) => {
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('session.cwd', async () => ({ value: '/repo' }))
  on('process.run', async (_$, e) => {
    const argv = e.argv.join(' ')
    const out = argv.includes('rev-parse')
      ? '/repo\n'
      : argv.includes('ls-files')
        ? FILES
        : argv.includes('status')
          ? STATUS
          : ''
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.call', async () => ({ result: { type: 'update', filePath: '/repo/src/util.ts' } as never }))

  await $.command.run({ command: 'files' } as never)
  await $.tool.call({
    tool: 'Edit',
    file_path: '/repo/src/util.ts',
    old_string: 'a',
    new_string: 'b',
  } as never)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({
      plugin: 'session-files',
      surface,
      component: 'Pane',
      requestId: 'session-files',
      props: { title: 'Files', isFocused: false, bodyColumns: 60, placement: 'dock' } as never,
    })
    expect(await ui.find({ text: /1 edited by Claude · 5 changed/ })).toBeDefined()
    expect(await ui.find({ text: /util\.ts/ })).toBeDefined()
    expect(await ui.find({ text: / M/ })).toBeDefined()
    expect(await ui.find({ text: / !/ })).toBeDefined()
    expect(await ui.find({ text: / U/ })).toBeDefined()

    await ui.press({ key: 'mode' })
    expect(await ui.find({ text: /README\.md/ })).toBeUndefined()
    await ui.press({ key: 'mode' })
    expect(await ui.find({ text: /README\.md/ })).toBeDefined()
    await ui.unmount()
  }
})
