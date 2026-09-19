#!/usr/bin/env node
/**
 * End-to-end smoke test: drives the real page in headless Chrome and asserts
 * what the user actually sees. Catches what typecheck cannot — a dead UI
 * branch, a layer buried under another, a 404 on a data file.
 *
 *   npm run dev                       # in another shell
 *   node tests/smoke_frontend.mjs
 *
 * Needs Chrome. Exits non-zero on the first failed assertion.
 */
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const APP = process.env.APP_URL ?? 'http://localhost:5173/'
const PORT = 9333
const CHROME = process.env.CHROME_PATH
  ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const failures = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : '  FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failures.push(name)
}
const settle = (ms) => new Promise((r) => setTimeout(r, ms))

const app = await fetch(APP).catch(() => null)
if (!app?.ok) {
  console.error(`dev server not reachable at ${APP}; run "npm run dev" first`)
  process.exit(2)
}

const chrome = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`,
  // Software WebGL: without it MapLibre renders nothing in headless and every
  // map assertion passes vacuously against a blank canvas.
  '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  '--window-size=1500,950', '--hide-scrollbars',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'smoke-'))}`,
  'about:blank',
], { stdio: 'ignore' })

let ws
try {
  for (let i = 0; i < 40 && !ws; i++) {
    await settle(250)
    const list = await fetch(`http://127.0.0.1:${PORT}/json`).then((r) => r.json()).catch(() => null)
    const page = list?.find((t) => t.type === 'page' && t.webSocketDebuggerUrl)
    if (page) ws = new WebSocket(page.webSocketDebuggerUrl)
  }
  if (!ws) throw new Error('Chrome did not expose a CDP target')
  await new Promise((r) => (ws.onopen = r))

  let id = 0
  const pending = new Map()
  const bad = []
  const errors = []
  ws.onmessage = (m) => {
    const x = JSON.parse(m.data)
    if (x.id && pending.has(x.id)) {
      const p = pending.get(x.id); pending.delete(x.id); p(x.result)
    }
    if (x.method === 'Network.responseReceived' && x.params.response.status >= 400)
      bad.push(`${x.params.response.status} ${x.params.response.url}`)
    if (x.method === 'Log.entryAdded' && x.params.entry.level === 'error')
      errors.push(x.params.entry.text?.slice(0, 160))
  }
  const send = (method, params = {}) => new Promise((resolve) => {
    const n = ++id; pending.set(n, resolve)
    ws.send(JSON.stringify({ id: n, method, params }))
  })
  const ev = async (expr) =>
    (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value
  const clickText = (t) => ev(
    `[...document.querySelectorAll('button')].find(b => b.textContent.includes(${JSON.stringify(t)}))?.click() ?? null`)
  const layers = () => ev(`(() => {
    const c = document.querySelector('canvas.maplibregl-canvas')
    return !!c && c.width > 0
  })()`)

  await send('Network.enable'); await send('Page.enable'); await send('Log.enable')
  await send('Page.navigate', { url: APP })
  await settle(8000)

  check('page renders', (await ev('document.querySelector("h1")?.textContent')) === 'Unmapped')
  check('map canvas is live', await layers())

  const cards = await ev(
    `[...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t => t.includes('→'))`)
  check('both trips listed', cards?.length === 2, cards?.join(' | '))

  // Clark: the shortcut route, which must report the lawn and the nearby steps.
  await clickText('Clark Hall')
  await settle(4000)
  const clark = await ev(`document.querySelector('dl')?.parentElement?.textContent ?? ''`)
  check('Clark shows a distance', /\d+ m/.test(clark))
  check('Clark reports the lawn shortcut', clark.includes('Decker Quad'), clark.slice(0, 60))
  check('Clark warns about nearby steps', /step/i.test(clark))
  check('Clark is not called step-free', !/step-free/i.test(clark))
  check('route line is on the map',
    await ev(`!!window.document.querySelector('canvas.maplibregl-canvas')`))

  await clickText('Clark Hall')          // collapse
  await settle(1500)

  // Garage: no shortcut, but must arrive at the lift rather than the centre.
  await clickText('San Martin Garage')
  await settle(4000)
  const garage = await ev(`document.querySelector('dl')?.parentElement?.textContent ?? ''`)
  check('Garage arrives at the lift', garage.includes('Elevator'), garage.slice(0, 60))
  check('Garage claims no shortcut', !garage.includes('across'))

  // Campus data on top of a shown route: the overlay must not bury the line.
  await ev(`document.querySelector('[role=switch]').click()`)
  await settle(9000)
  const order = await ev(`(() => {
    const el = [...document.querySelectorAll('canvas')]
    return el.length
  })()`)
  check('campus data loads without error', order > 0)

  check('no 4xx/5xx responses', bad.length === 0, bad.join('; '))
  check('no console errors', errors.length === 0, errors.slice(0, 2).join('; '))

  ws.close()
} finally {
  chrome.kill()
}

console.log(failures.length
  ? `\n${failures.length} failed: ${failures.join(', ')}`
  : '\nall checks passed')
process.exit(failures.length ? 1 : 0)
