import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile, readdir, mkdir } from 'node:fs/promises';
import { resolve, extname, join } from 'node:path';
import { PROJECT, API, SESSION, fixture, mock, open } from './support/workspace.js';

const publicRoot = resolve('../worker/dist/public');
const shots = process.env.DESIGN_SHOTS_DIR;
const forbiddenCopy = /lorem|ipsum|\bacme\b|jane doe|\bTODO\b|\u2014|iPhone(?! Duo\b)/i;
const pending = () => fixture({ status: 'awaiting_approval', stage: 'Release gate', progress: 0.75,
  summary: 'Checks are ready. Review the pending release action in Notify.',
  checks: fixture().checks.map((check, index) => ({ ...check, status: index < 3 ? 'passed' : 'pending' })),
  approval: { requestId: 'browser_test_approval', digest: 'a'.repeat(64), title: 'Publish the release candidate', status: 'pending' } });

// Inspect text nodes, control values, placeholders and generated text. A correct
// body font alone does not establish the font of a nested element/native control.
async function assertDesign(page) {
  await page.evaluate(() => document.fonts.ready);
  const report = await page.evaluate(() => {
    const visible = node => node.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    const paper = font => /^['"]?Paper Mono['"]?(?:,|$)/.test(font);
    const rgb = value => value.match(/[\d.]+/g)?.map(Number) || [];
    const luminance = color => color.slice(0, 3).map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
    const fonts = [], contrast = [], decorations = [];
    let count = 0;
    for (const node of document.body.querySelectorAll('*')) {
      if (!visible(node)) continue;
      const style = getComputedStyle(node);
      if (style.boxShadow !== 'none' || style.backgroundImage.includes('gradient(') || style.animationName !== 'none') decorations.push(node.id || node.tagName);
      const ownText = [...node.childNodes].some(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
      const control = node.matches('button,input,textarea,select,option');
      const parts = [{ style, text: ownText || control, part: '' }];
      if (node.matches('input[placeholder],textarea[placeholder]')) parts.push({ style: getComputedStyle(node, '::placeholder'), text: true, part: '::placeholder' });
      for (const pseudo of ['::before', '::after']) {
        const pseudoStyle = getComputedStyle(node, pseudo);
        if (!['none', 'normal', '""'].includes(pseudoStyle.content)) parts.push({ style: pseudoStyle, text: true, part: pseudo });
      }
      for (const part of parts) {
        if (!part.text) continue;
        count++;
        const label = `${node.tagName.toLowerCase()}#${node.id}${part.part}`;
        if (!paper(part.style.fontFamily)) fonts.push({ label, font: part.style.fontFamily });
        let background = node;
        let back;
        do {
          back = rgb(getComputedStyle(background).backgroundColor);
          if (back.length === 3 || back[3] === 1) break;
          background = background.parentElement;
        } while (background);
        const light = [luminance(rgb(part.style.color)), luminance(back)].sort((a, b) => a - b);
        const ratio = (light[1] + 0.05) / (light[0] + 0.05);
        if (ratio < 4.5) contrast.push({ label, ratio });
      }
    }
    return { fonts, contrast, decorations, count,
      loaded: [...document.fonts].some(font => font.family === 'Paper Mono' && font.status === 'loaded'),
      overflow: document.documentElement.scrollWidth > innerWidth,
      badImages: [...document.images].filter(visible).filter(img => !img.complete || !img.naturalWidth).map(img => img.src),
      motion: [...document.querySelectorAll('button,a')].filter(visible).some(node => getComputedStyle(node).transitionDuration !== '0s'),
    };
  });
  expect(report.count).toBeGreaterThan(0);
  expect(report.fonts, 'Every visible text element and placeholder must start with Paper Mono').toEqual([]);
  expect(report.loaded, 'Official font must load, not just appear in a fallback list').toBe(true);
  expect(report.contrast, 'All text, including placeholders, must reach AA contrast').toEqual([]);
  expect(report.overflow).toBe(false);
  expect(report.decorations).toEqual([]);
  expect(report.badImages).toEqual([]);
  expect(report.motion).toBe(false);
  expect(await page.locator('body').innerText()).not.toMatch(forbiddenCopy);
  if (!await page.locator('#workspace').isVisible()) await expect(page.locator('#reply-link')).toBeHidden();
  await expect(page.locator('.brand-mark')).toHaveAttribute('src', '/logos/nous-research.png');
  await expect(page.locator('.provider-credit img')).toHaveAttribute('src', '/logos/notify.svg');
  for (const control of ['#sign-in', '#auth-help', '#native-approval']) {
    if (await page.locator(control).isVisible()) await expect(page.locator(`${control} img`)).toHaveAttribute('src', '/logos/notify.svg');
  }
  const imageTreatment = await page.locator('img').evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node);
    return { src: node.getAttribute('src'), filter: style.filter, mask: style.maskImage, fit: style.objectFit };
  }));
  for (const treatment of imageTreatment) {
    expect(['/logos/nous-research.png', '/logos/notify.svg']).toContain(treatment.src);
    expect(treatment.filter).toBe('none');
    expect(treatment.mask).toBe('none');
    expect(treatment.fit).toBe('contain');
  }
}

const states = ['signed-out', 'loading', 'pending-decision', 'release-complete', 'error', 'empty', 'empty-release', 'auth-error', 'root', 'not-found', 'service-error'];
async function showState(page, state) {
  if (state === 'root') {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Open a project link' })).toBeVisible();
  } else if (state === 'not-found' || state === 'service-error') {
    const response = await page.goto(state === 'not-found' ? '/not-a-page' : '/__design/service-error');
    expect(response.status()).toBe(state === 'not-found' ? 404 : 503);
    await expect(page.getByRole('heading', { name: state === 'not-found' ? 'Page not found' : 'Workspace temporarily unavailable' })).toBeVisible();
  } else if (state === 'loading') {
    await mock(page, { sessionHandler: () => {} });
    await page.goto(`/projects/${PROJECT}`);
    await expect(page.getByRole('heading', { name: 'Opening workspace' })).toBeVisible();
  } else if (state === 'signed-out' || state === 'auth-error') {
    await mock(page, { signedIn: false, realAuth: true });
    await page.goto(`/projects/${PROJECT}`);
    await expect(page.getByRole('heading', { name: 'Your release workspace' })).toBeVisible();
    if (state === 'auth-error') {
      await page.getByRole('button', { name: 'Sign in with Notify' }).click();
      await expect(page.getByRole('heading', { name: 'Sign-in not completed' })).toBeVisible();
    }
  } else if (state === 'empty' || state === 'error') {
    await mock(page, { workspaceHandler: route => route.fulfill({ status: state === 'empty' ? 404 : 503, json: { error: 'unavailable' } }) });
    await page.goto(`/projects/${PROJECT}`);
    await expect(page.getByRole('heading', { name: state === 'empty' ? 'No release published' : 'Could not load this release' })).toBeVisible();
  } else {
    const workspace = state === 'pending-decision' ? pending() : state === 'empty-release'
      ? fixture({ status: 'preparing', name: '', version: '', stage: '', summary: '', progress: null, checks: [], artifacts: [], notes: '' })
      : fixture({ status: 'shipped', stage: 'Release finished', progress: 1,
        summary: 'The release finished. Artifacts and rollback notes are available below.',
        checks: fixture().checks.map(check => ({ ...check, status: 'passed' })),
      });
    await mock(page, { workspace });
    await open(page);
  }
}

for (const width of [390, 900]) {
  for (const state of states) {
    test(`${state} at ${width}px has consistent fonts, copy, contrast and marks`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      await showState(page, state);
      await assertDesign(page);
      if (shots) {
        await mkdir(shots, { recursive: true });
        await page.screenshot({ path: join(shots, `${state}-${width}.png`), fullPage: true });
      }
      await testInfo.attach('design-state', { body: `${state}, ${width}x844, production Worker assets; synthetic private API responses`, contentType: 'text/plain' });
    });
  }
}

for (const width of [320, 360, 430]) {
  test(`phone layout at ${width}px has no clipping and retains touch targets`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await showState(page, 'pending-decision');
    await assertDesign(page);
    const small = await page.locator('a,button,textarea').evaluateAll(nodes => nodes.filter(node => node.checkVisibility()).filter(node => {
      const rect = node.getBoundingClientRect();
      return rect.width < 44 || rect.height < 44;
    }).map(node => node.textContent));
    expect(small).toEqual([]);
  });
}

test('native inputs, selects and their placeholders inherit Paper Mono', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => {
    const controls = document.createElement('form');
    controls.innerHTML = '<label>Filter<input placeholder="Filter releases"></label><label>State<select><option>All releases</option></select></label><label>Notes<textarea placeholder="Release notes"></textarea></label><button type="button">Apply filter</button>';
    document.querySelector('main').append(controls);
  });
  await assertDesign(page);
});

test('hover and focus keep enabled and disabled controls legible', async ({ page }) => {
  await showState(page, 'pending-decision');
  await page.getByRole('button', { name: 'Send reply', exact: true }).hover();
  await assertDesign(page);
  await page.getByLabel('Your reply').fill('Please attach the verification report.');
  for (const control of ['#send-reply', '#native-approval', '#refresh', '#sign-out', '#reply-text']) {
    await page.locator(control).hover();
    await page.locator(control).focus();
    await assertDesign(page);
  }
});

test('all remaining release statuses and reply outcomes retain the design', async ({ page }) => {
  const state = await mock(page);
  await open(page);
  let revision = 4;
  for (const status of ['running', 'approved', 'failed', 'denied', 'canceled']) {
    state.setWorkspace(fixture({ revision: ++revision, status }));
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.locator('#release-status')).toHaveAttribute('data-status', status);
    await assertDesign(page);
  }
  await page.getByLabel('Your reply').fill('Please attach the verification report.');
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.locator('#reply-feedback')).toContainText('Reply saved');
  await assertDesign(page);
  await page.getByRole('button', { name: 'Write another reply' }).click();
  await page.route(`**${API}/replies`, route => route.fulfill({ status: 503, json: { error: 'unavailable' } }));
  await page.getByLabel('Your reply').fill('Please include recovery instructions.');
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry reply' })).toBeVisible();
  await assertDesign(page);
  await page.route(`**${SESSION}`, route => route.fulfill({ status: 503, json: { error: 'unavailable' } }));
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sign-out needs a retry' })).toBeVisible();
  await assertDesign(page);
});

test('no-script recovery uses the same font and actionable copy', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:' + (process.env.APP_TEST_PORT || 4179) + '/');
  await expect(page.getByRole('heading', { name: 'Enable JavaScript' })).toBeVisible();
  await expect(page.locator('#gate')).toBeHidden();
  await assertDesign(page);
  await context.close();
});

test('served UI assets meet copy rules and official font/logo bytes match provenance', async ({ request }) => {
  async function inspect(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const file = join(directory, entry.name);
      if (entry.isDirectory()) await inspect(file);
      else if (['.html', '.js', '.mjs', '.css', '.svg'].includes(extname(file))) {
        const path = file.slice(publicRoot.length).replaceAll('\\', '/');
        const response = await request.get(path);
        expect(response.status(), path).toBe(200);
        expect(await response.text(), path).not.toMatch(forbiddenCopy);
        expect(await response.text(), path).not.toMatch(/\bBelweave\b/);
      }
    }
  }
  await inspect(publicRoot);
  const logos = JSON.parse(await readFile(join(publicRoot, 'logos/PROVENANCE.json'), 'utf8'));
  expect(logos.map(logo => logo.provider)).toEqual(['Nous Research / Hermes Agent', 'Notify']);
  for (const logo of logos) {
    expect(logo.source).toMatch(/^https:\/\/(nousresearch\.com|notify\.belweave\.ai)\//);
    expect(logo.retrievedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(logo.note).toBeTruthy();
    const response = await request.get(`/logos/${logo.file}`);
    expect(response.status()).toBe(200);
    expect(createHash('sha256').update(await response.body()).digest('hex')).toBe(logo.sha256);
  }
  const font = await request.get('/fonts/PaperMono-Variable.woff2');
  expect(createHash('sha256').update(await font.body()).digest('hex')).toBe('57b28aaaffc46f85ed5b5adeda22bc7bce0fcdbf3e6f84850c327765fe6fdc6b');
  expect(await (await request.get('/fonts/LICENSE.txt')).text()).toContain('SIL OPEN FONT LICENSE');
  for (const path of ['/not-a-page', '/__design/service-error']) {
    const response = await request.get(path, { headers: { accept: 'text/html' } });
    expect(await response.text()).not.toMatch(forbiddenCopy);
  }
});
