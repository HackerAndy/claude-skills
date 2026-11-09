import { chromium } from 'playwright';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';

export async function launchBrowser(headless = true) {
  const opts = { headless };
  return chromium.launch(opts).catch(() =>
    chromium.launch({ ...opts, channel: process.env.UX_AUDIT_CHANNEL || 'msedge' }));
}

export function authFileFor(url) {
  return resolve(process.cwd(), '.ux-auth', `${new URL(url).host.replace(/:/g, '_')}.json`);
}

// Playwright storageState omits sessionStorage (where MSAL keeps tokens), so it is saved and restored separately.
export async function newContext(browser, { viewport, authPath } = {}) {
  const saved = authPath && existsSync(authPath) ? JSON.parse(readFileSync(authPath, 'utf8')) : null;
  const context = await browser.newContext({ viewport: viewport ?? { width: 1280, height: 800 }, storageState: saved?.storage });
  if (saved?.session && Object.keys(saved.session).length) {
    await context.addInitScript(({ origin, data }) => {
      if (location.origin === origin) for (const [k, v] of Object.entries(data)) sessionStorage.setItem(k, v);
    }, { origin: saved.origin, data: saved.session });
  }
  return context;
}

export async function saveAuth(context, page, authPath, origin) {
  if (!page.url().startsWith(origin)) return false;
  const session = await page.evaluate(() => ({ ...sessionStorage }));
  const storage = await context.storageState();
  mkdirSync(dirname(authPath), { recursive: true });
  writeFileSync(authPath, JSON.stringify({ origin, storage, session }, null, 2));
  return true;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
