const fs = require('fs');
const path = require('path');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(process.env.HOME, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
(async () => {
  const browser = await playwright.chromium.launch({headless: true, executablePath: process.argv[4]});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.request().url().startsWith('file:') ? route.continue() : route.abort());
    await page.goto(require('url').pathToFileURL(process.argv[2]).href);
    await page.pdf({path: process.argv[3], format: 'Letter', printBackground: true, preferCSSPageSize: true});
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
