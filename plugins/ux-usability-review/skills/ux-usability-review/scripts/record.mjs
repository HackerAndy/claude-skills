import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, relative } from 'node:path';
import { launchBrowser, newContext, authFileFor, saveAuth, sleep } from './lib.mjs';

// Runs inside every page of the recorded browser.
function pageRecorder() {
  if (window.top !== window) return;
  const esc = (s) => s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const clean = (s) => (s || '').trim().replace(/\s+/g, ' ');
  const CLICKABLE = 'a,button,[role=button],[role=tab],[role=menuitem],[role=link],[role=option],input[type=submit],label,summary';
  const text = (el) => clean(el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('title'));
  const base = (el) => {
    const tid = el.getAttribute('data-testid');
    if (tid) return { css: `[data-testid="${esc(tid)}"]` };
    if (el.id && !/\d{3,}|^:r|^mui/.test(el.id)) return { css: `#${CSS.escape(el.id)}` };
    const tag = el.tagName.toLowerCase();
    if (['input', 'textarea', 'select'].includes(tag)) {
      for (const a of ['aria-label', 'name', 'placeholder']) {
        const v = el.getAttribute(a);
        if (v) return { css: `${tag}[${a}="${esc(v)}"]` };
      }
      const lab = clean(el.labels?.[0]?.innerText);
      if (lab) return { css: `${tag}`, label: lab };
      return { css: tag };
    }
    const t = text(el);
    const role = el.getAttribute('role');
    const kind = role ? `[role="${role}"]` : tag;
    if (t && t.length <= 60) {
      const same = [...document.querySelectorAll(kind)].filter((e) => text(e) === t);
      const idx = same.indexOf(el);
      const sel = `${kind}:text-is("${esc(t)}")`;
      return { css: same.length > 1 ? `${sel} >> nth=${idx}` : sel };
    }
    return { css: tag };
  };
  const selector = (el) => {
    const b = base(el);
    if (b.label) {
      const same = [...document.querySelectorAll('input,textarea,select')].filter((e) => clean(e.labels?.[0]?.innerText) === b.label);
      return `label:has-text("${esc(b.label)}") >> ${b.css}` + (same.length > 1 ? ` >> nth=${same.indexOf(el)}` : '');
    }
    return b.css;
  };
  const send = (step) => window.__uxRec(step);

  document.addEventListener('click', (e) => {
    const el = e.target.closest?.(CLICKABLE) || e.target;
    const tag = el.tagName?.toLowerCase();
    if (['input', 'textarea', 'select'].includes(tag) && !['submit', 'checkbox', 'radio', 'button'].includes(el.type)) return;
    if (tag === 'option' || tag === 'select') return;
    if (tag === 'label' && el.control && el.control !== el) return;
    const t = text(el);
    send({ name: `Click "${t || tag}"`, click: selector(el) });
  }, true);

  document.addEventListener('change', (e) => {
    const el = e.target;
    const tag = el.tagName?.toLowerCase();
    if (!['input', 'textarea', 'select'].includes(tag) || ['checkbox', 'radio'].includes(el.type)) return;
    const label = clean(el.labels?.[0]?.innerText || el.getAttribute('aria-label') || el.placeholder || el.name || tag);
    const value = el.type === 'password' ? '<password>' : el.value;
    send({ name: `Enter "${label}"`, fill: { selector: selector(el), value }, snapshot: false });
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
      send({ name: 'Press Enter', press: { selector: selector(e.target), key: 'Enter' } });
    }
  }, true);

  const badge = () => {
    if (document.getElementById('__ux_rec_badge')) return;
    const b = document.createElement('div');
    b.id = '__ux_rec_badge';
    b.textContent = 'REC  Click through like a first-time user. Close this window when done.';
    b.style.cssText = 'position:fixed;bottom:8px;right:8px;z-index:2147483647;background:#b00020;color:#fff;font:12px sans-serif;padding:6px 10px;border-radius:4px;pointer-events:none;opacity:.9';
    document.documentElement.appendChild(b);
  };
  document.addEventListener('DOMContentLoaded', badge);
  window.addEventListener('load', badge);
}

export async function recordSession({ url, name, goal, drive, headless = false }) {
  const origin = new URL(url).origin;
  const authPath = authFileFor(url);
  const hasAuth = existsSync(authPath);
  const browser = await launchBrowser(headless);
  const context = await newContext(browser, { authPath: hasAuth ? authPath : undefined });
  const steps = [];
  await context.exposeBinding('__uxRec', (_src, step) => {
    const last = steps[steps.length - 1];
    if (step.fill && last?.fill?.selector === step.fill.selector) steps.pop();
    steps.push(step);
  });
  await context.addInitScript(pageRecorder);
  const page = await context.newPage();
  let closed = false;
  browser.on('disconnected', () => { closed = true; });
  page.on('framenavigated', (f) => {
    if (f !== page.mainFrame()) return;
    const u = new URL(f.url());
    if (u.origin === origin && steps.length === 0) steps.push({ name: 'Open start page', goto: u.pathname + u.search });
  });
  await page.goto(url).catch(() => {});
  console.log('Recording. Do the task as a first-time user would, then CLOSE the browser window to save.');
  if (drive) { await drive(page); await browser.close(); } else { while (!closed) await sleep(500); }

  const slug = (name || new URL(url).host).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();
  const dir = resolve(process.cwd(), 'ux-flows');
  mkdirSync(dir, { recursive: true });
  const file = resolve(dir, `${slug}.flow.json`);
  const flow = {
    name: name || slug,
    baseUrl: origin,
    goal: goal || 'A first-time user completes the recorded task',
    auth: hasAuth ? relative(process.cwd(), authPath).replace(/\\/g, '/') : null,
    viewport: { width: 1280, height: 800 },
    steps,
  };
  writeFileSync(file, JSON.stringify(flow, null, 2));
  console.log(`Saved ${steps.length} steps to ${relative(process.cwd(), file)}`);
  return file;
}

export async function loginSession({ url, headless = false, drive }) {
  const origin = new URL(url).origin;
  const authPath = authFileFor(url);
  const browser = await launchBrowser(headless);
  const context = await newContext(browser, {});
  const page = await context.newPage();
  let closed = false;
  browser.on('disconnected', () => { closed = true; });
  await page.goto(url).catch(() => {});
  console.log('Sign in as a normal user, wait for the app to load, then CLOSE the browser window.');
  if (drive) await drive(page);
  let saved = false;
  while (!closed) {
    try { saved = (await saveAuth(context, page, authPath, origin)) || saved; } catch { /* mid-navigation */ }
    if (drive) break;
    await sleep(1500);
  }
  if (drive) await browser.close();
  console.log(saved ? `Session saved to ${relative(process.cwd(), authPath)} (git-ignored; tokens expire, re-run login when audits redirect to sign-in).`
    : 'No signed-in app page was seen, nothing saved.');
  return saved;
}
