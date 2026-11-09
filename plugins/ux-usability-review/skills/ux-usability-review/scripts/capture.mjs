import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { launchBrowser, newContext } from './lib.mjs';

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const flowPath = opt('flow');
if (!flowPath) { console.error('Usage: node capture.mjs --flow <file> [--out dir] [--base-url url] [--min-score n]'); process.exit(2); }
const out = resolve(opt('out', './ux-audit-out'));
const minScore = Number(opt('min-score', 0));
const flow = JSON.parse(readFileSync(flowPath, 'utf8'));
const baseUrl = opt('base-url', flow.baseUrl);
mkdirSync(out, { recursive: true });

const GENERIC = /^(submit|ok|click here|here|go|continue|next|more|details|yes|no|send|apply|save|done)$/i;
const JARGON = /\b(payload|schema|entity|provision|instantiate|tenant|sku|uuid|oauth|rbac|etl|api|cfg|config|param|dto|crud|idempotent|namespace)\b/i;

function syllables(w) {
  w = w.toLowerCase().replace(/[^a-z]/g, '');
  if (!w) return 0;
  const m = w.replace(/e$/, '').match(/[aeiouy]+/g);
  return Math.max(1, m ? m.length : 1);
}
function gradeLevel(text) {
  const sentences = text.split(/[.!?]+\s/).filter((s) => s.trim().split(/\s+/).length > 2);
  const words = text.split(/\s+/).filter((w) => /[a-z]/i.test(w));
  if (!sentences.length || words.length < 15) return null;
  const syl = words.reduce((a, w) => a + syllables(w), 0);
  return +(0.39 * (words.length / sentences.length) + 11.8 * (syl / words.length) - 15.59).toFixed(1);
}

async function observe(page) {
  return page.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const name = (el) => (el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') || el.getAttribute('placeholder') || el.value || '').trim().replace(/\s+/g, ' ');
    const controls = [...document.querySelectorAll('a[href],button,[role=button],[role=link],input,select,textarea,[role=tab],[role=menuitem]')]
      .filter(vis).map((el) => {
        const r = el.getBoundingClientRect();
        const id = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        return { tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), role: el.getAttribute('role'),
          text: name(el), hasLabel: !!(id || el.closest('label') || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')),
          placeholder: el.getAttribute('placeholder'), required: el.required || el.getAttribute('aria-required') === 'true',
          disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
          explained: !!(el.title || el.getAttribute('aria-describedby')),
          aboveFold: r.top < innerHeight, area: Math.round(r.width * r.height) };
      });
    const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(vis)
      .map((h) => ({ level: +h.tagName[1], text: h.innerText.trim() }));
    const images = [...document.querySelectorAll('img')].filter(vis).map((i) => ({ alt: i.getAttribute('alt') }));
    const alerts = [...document.querySelectorAll('[role=alert],[aria-live]')].map((a) => a.innerText.trim()).filter(Boolean);
    return { title: document.title, url: location.href, headings, controls, images, alerts,
      text: document.body.innerText, hasMain: !!document.querySelector('main,[role=main]'),
      hasNav: !!document.querySelector('nav,[role=navigation]') };
  });
}

function analyze(ev, prev) {
  const flags = [];
  const add = (severity, code, msg, evidence) => flags.push({ severity, code, msg, evidence });
  const ctrls = ev.controls;
  const buttons = ctrls.filter((c) => c.tag === 'button' || c.role === 'button' || c.type === 'submit');
  const inputs = ctrls.filter((c) => ['input', 'select', 'textarea'].includes(c.tag) && c.type !== 'hidden');

  if (!ev.headings.length) add('major', 'no-heading', 'No heading tells the user what this page is for.');
  else if (!ev.headings.some((h) => h.level === 1)) add('minor', 'no-h1', 'No h1 heading.', ev.headings[0].text);
  if (!ev.title || /^(vite|react app|untitled)/i.test(ev.title)) add('minor', 'weak-title', 'Document title is missing or default.', ev.title);

  for (const c of ctrls) {
    if (!c.text && c.tag !== 'input') add('major', 'unnamed-control', 'Control has no accessible name (icon-only?).', c.tag);
    if (GENERIC.test(c.text)) add('minor', 'generic-label', 'Generic label does not say what will happen.', c.text);
    if (JARGON.test(c.text)) add('minor', 'jargon-label', 'Label contains technical jargon.', c.text);
    if (/^[A-Z0-9]{2,6}$/.test(c.text) && !/^(OK|GO)$/.test(c.text)) add('minor', 'acronym-label', 'Unexplained acronym in a label.', c.text);
  }
  for (const i of inputs) {
    if (!i.hasLabel && i.placeholder) add('major', 'placeholder-as-label', 'Input relies on placeholder as its only label.', i.placeholder);
    else if (!i.hasLabel) add('major', 'unlabelled-input', 'Input has no label.', i.type || 'input');
  }
  for (const im of ev.images) if (im.alt === null) add('minor', 'missing-alt', 'Image without alt attribute.');

  const aboveFoldButtons = buttons.filter((b) => b.aboveFold && b.text);
  for (const b of aboveFoldButtons.filter((x) => x.disabled && !x.explained))
    add('major', 'disabled-action-unexplained', 'Visible action is disabled and nothing says why.', b.text);
  const errLine = ev.text.split('\n').map((l) => l.trim()).find((l) => l && l.length < 200 &&
    /\b(internal server error|something went wrong|unable to|failed to|not configured|service degraded|unavailable|\d{3} error)\b/i.test(l));
  if (errLine) add('major', 'error-text-visible', 'Error or degraded-state text is visible on the page.', errLine);
  if (!aboveFoldButtons.length && buttons.length) add('major', 'no-primary-above-fold', 'No action button visible above the fold.');
  if (buttons.length > 8) add('minor', 'many-buttons', `${buttons.length} buttons compete for attention.`);
  if (ctrls.length > 30) add('major', 'too-many-controls', `${ctrls.length} interactive elements on one screen.`);
  if (!ctrls.length) add('blocker', 'dead-end', 'No interactive elements: user has nowhere to go.');
  if (!ev.hasNav && !ev.hasMain) add('minor', 'no-landmarks', 'No nav/main landmarks to orient the user.');

  const grade = gradeLevel(ev.text);
  if (grade !== null && grade > 10) add('minor', 'hard-to-read', `Reading grade ~${grade}; target <= 8.`);
  const words = ev.text.split(/\s+/).filter(Boolean).length;
  if (words > 400) add('minor', 'text-heavy', `${words} words of text on screen.`);

  if (prev && prev.url === ev.url && prev.text === ev.text && ev.step.action)
    add('major', 'no-visible-feedback', 'Action produced no visible change (no feedback).', ev.step.name);

  const penalty = { blocker: 40, major: 12, minor: 4 };
  const score = Math.max(0, 100 - flags.reduce((a, f) => a + penalty[f.severity], 0));
  return { step: ev.step.name, url: ev.url, score,
    metrics: { controls: ctrls.length, buttons: buttons.length, inputs: inputs.length, words, readingGrade: grade, headings: ev.headings.length },
    flags };
}

const browser = await launchBrowser(true);
const context = await newContext(browser, { viewport: flow.viewport, authPath: flow.auth ? resolve(process.cwd(), flow.auth) : undefined });
const page = await context.newPage();
const evidence = []; const results = []; let prev = null;

for (const [i, step] of flow.steps.entries()) {
  const startUrl = page.url();
  try {
    if (step.goto !== undefined) await page.goto(new URL(step.goto, baseUrl).href, { waitUntil: 'networkidle' });
    else if (step.click) await page.click(step.click);
    else if (step.fill) await page.fill(step.fill.selector, step.fill.value);
    else if (step.press) await page.press(step.press.selector, step.press.key);
    await page.waitForLoadState('networkidle').catch(() => {});
  } catch (e) {
    results.push({ step: step.name, url: page.url(), score: 0, metrics: {}, flags: [{ severity: 'blocker', code: 'step-failed', msg: String(e.message).split('\n')[0], evidence: JSON.stringify(step) }] });
    evidence.push({ step, error: String(e.message).split('\n')[0] });
    break;
  }
  if (step.snapshot === false) continue;
  const ev = await observe(page);
  ev.step = { ...step, action: !!(step.click || step.press), index: i + 1, fromUrl: startUrl };
  await page.screenshot({ path: `${out}/step-${i + 1}.png`, fullPage: true });
  evidence.push(ev);
  const res = analyze(ev, prev);
  if (flow.auth && /login\.microsoftonline\.com|\/login|signin/i.test(page.url()) && !new URL(baseUrl).host.includes(new URL(page.url()).host)) {
    res.flags.push({ severity: 'blocker', code: 'auth-expired', msg: 'Redirected to sign-in; saved session is missing or expired. Run: cli.mjs login <url>', evidence: page.url() });
    res.score = 0;
  }
  results.push(res);
  prev = ev;
}
await browser.close();

const summary = { flow: flow.name, goal: flow.goal, steps: flow.steps.length, executed: results.length,
  clicksToGoal: flow.steps.filter((s) => s.click).length,
  averageScore: results.length ? Math.round(results.reduce((a, r) => a + r.score, 0) / results.length) : 0 };
writeFileSync(`${out}/evidence.json`, JSON.stringify({ flow: flow.name, goal: flow.goal, steps: evidence }, null, 2));
writeFileSync(`${out}/heuristics.json`, JSON.stringify({ summary, results }, null, 2));

for (const r of results) console.log(`[${r.score}] ${r.step} (${r.flags.length} flags)`);
console.log(`Average heuristic score: ${summary.averageScore}. Output: ${out}`);
const blocked = results.some((r) => r.flags.some((f) => f.severity === 'blocker'));
process.exit(blocked || (minScore && results.some((r) => r.score < minScore)) ? 1 : 0);
