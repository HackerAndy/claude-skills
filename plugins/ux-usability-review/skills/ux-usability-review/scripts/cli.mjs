#!/usr/bin/env node
// One entry point: setup | login <url> | record <url> | audit [flow files]
// Run from the root of the project being audited; flows, auth and output live there.
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, mkdirSync, appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const [cmd, ...rest] = process.argv.slice(2);
const flag = (n) => { const i = rest.indexOf(`--${n}`); return i >= 0 ? rest[i + 1] : undefined; };
const positional = rest.filter((a, i) => !a.startsWith('--') && !(rest[i - 1] ?? '').startsWith('--'));
const run = (c, a, opts = {}) => spawnSync(c, a, { stdio: 'inherit', shell: process.platform === 'win32', ...opts });

function setup() {
  if (!existsSync(resolve(here, 'node_modules', 'playwright'))) {
    console.log('First run: installing the capture tool (about a minute)...');
    if (run('npm', ['install', '--silent'], { cwd: here }).status !== 0) process.exit(1);
    run('npx', ['playwright', 'install', 'chromium'], { cwd: here });
  }
  const gi = resolve(process.cwd(), '.gitignore');
  const cur = existsSync(gi) ? readFileSync(gi, 'utf8') : '';
  const missing = ['.ux-auth/', 'ux-audit-out/'].filter((l) => !cur.split(/\r?\n/).includes(l));
  if (missing.length) appendFileSync(gi, `${cur && !cur.endsWith('\n') ? '\n' : ''}${missing.join('\n')}\n`);
}

if (cmd === 'setup') setup();
else if (cmd === 'login' || cmd === 'record') {
  const url = positional[0];
  if (!url) { console.error(`Usage: cli.mjs ${cmd} <url> [--name n] [--goal g]`); process.exit(2); }
  setup();
  const { recordSession, loginSession } = await import('./record.mjs');
  if (cmd === 'login') await loginSession({ url });
  else await recordSession({ url, name: flag('name'), goal: flag('goal') });
  process.exit(0);
} else if (cmd === 'audit') {
  setup();
  const dir = resolve(process.cwd(), 'ux-flows');
  const files = positional.length ? positional.map((f) => resolve(f))
    : existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith('.flow.json')).map((f) => resolve(dir, f)) : [];
  if (!files.length) { console.error('No flows found in ./ux-flows. Ask Claude to draft some, or run: record <url>'); process.exit(2); }
  let failed = false;
  for (const f of files) {
    const out = resolve(process.cwd(), 'ux-audit-out', basename(f).replace(/\.flow\.json$/, ''));
    mkdirSync(out, { recursive: true });
    console.log(`\n== ${basename(f)}`);
    const r = run('node', [resolve(here, 'capture.mjs'), '--flow', f, '--out', out, ...rest.filter((a) => a.startsWith('--') || /^\d+$/.test(a))]);
    failed ||= r.status !== 0;
  }
  console.log('\nEvidence is in ux-audit-out/. Ask Claude: "write the UX report from ux-audit-out".');
  process.exit(failed ? 1 : 0);
} else {
  console.log('Usage:\n  cli.mjs login  <url>          sign in once (saved locally)\n  cli.mjs record <url> [--name n] [--goal g]   click through a task\n  cli.mjs audit  [flow files] [--min-score n]  run every flow in ./ux-flows');
  process.exit(cmd ? 2 : 0);
}
