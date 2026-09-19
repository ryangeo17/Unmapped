#!/usr/bin/env node
/**
 * End-to-end smoke test: drives the real page in headless Chrome and asserts
 * what the user actually sees. Catches what typecheck cannot — a dead UI
 * branch, a layer buried under another, a route that never reaches the map.
 *
 *   uvicorn planner.server:app --host 127.0.0.1   # in one shell
 *   npm --prefix frontend run dev                 # in another
 *   node tests/smoke_frontend.mjs
 *
 * Needs Chrome. Exits non-zero on the first failed assertion.
 */
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const APP = process.env.APP_URL ?? 'http://localhost:5173/'
const API = process.env.API_URL ?? 'http://127.0.0.1:8000'
const PORT = 9333
const CHROME = process.env.CHROME_PATH
  ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const failures = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : '  FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failures.push(name)
}
const settle = (ms) => new Promise((r) => setTimeout(r, ms))

for (const [what, url] of [['dev server', APP], ['planner API', `${API}/places`]]) {
  const res = await fetch(url).catch(() => null)
  if (!res?.ok) {
    console.error(`${what} not reachable at ${url}`)
    process.exit(2)
  }
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

try {
  let ws
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
    if (x.id && pending.has(x.id)) { const p = pending.get(x.id); pending.delete(x.id); p(x.result) }
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

  // Two role=switch exist — campus data, and the planner. Always scope to the
  // form, or you silently toggle the wrong one and the test passes anyway.
  const smarter = {
    toggle: () => ev(`document.querySelector('form [role=switch]').click()`),
    state: () => ev(`document.querySelector('form [role=switch]').getAttribute('aria-checked')`),
  }
  const setField = (label, value) => ev(`(() => {
    const l = [...document.querySelectorAll('label')].find(x => x.textContent.startsWith(${JSON.stringify(label)}))
    const i = l.querySelector('input')
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(i, ${JSON.stringify(value)})
    i.dispatchEvent(new Event('input', { bubbles: true }))
    return i.value })()`)
  const submit = () => ev(`document.querySelector('form button[type=submit]').click()`)
  const panel = () => ev(`document.querySelector('form')?.parentElement?.textContent ?? ''`)
  const routeDrawn = () => ev(`(() => {
    const m = document.querySelector('canvas.maplibregl-canvas')
    return !!m && m.width > 0 })()`)

  await send('Network.enable'); await send('Page.enable'); await send('Log.enable')
  await send('Page.navigate', { url: APP })
  await settle(8000)

  check('page renders', (await ev('document.querySelector("h1")?.textContent')) === 'Unmapped')
  check('map canvas is live', await routeDrawn())
  check('place list loaded from the API',
    (await ev(`document.querySelectorAll('#campus-places option').length`)) > 50)

  // Smarter on: the garage trip must reach the lift and report the saving.
  await setField('From', 'Malone Hall')
  await setField('To', 'San Martin Garage')
  check('smarter defaults on', (await smarter.state()) === 'true')
  await submit(); await settle(4000)
  const on = await panel()
  check('smarter route arrives at the lift', on.includes('Elevator'), on.slice(-90))
  check('smarter route reports what it saved', /shorter than the paved route/.test(on))
  check('route is on the map', await routeDrawn())

  // Smarter off: the same trip should get longer and end somewhere else.
  await smarter.toggle(); await settle(400)
  check('toggle flips', (await smarter.state()) === 'false')
  await submit(); await settle(4000)
  const off = await panel()
  check('plain route ends at the building centre', off.includes('building centre'),
    off.slice(-90))
  check('plain route is different from the smarter one', off !== on)

  // Ambiguity must be offered, not guessed.
  await smarter.toggle(); await settle(300)
  await setField('To', 'the garage')
  await submit(); await settle(4000)
  const ambiguous = await panel()
  check('ambiguous name offers candidates',
    ambiguous.includes('San Martin Garage') && ambiguous.includes('South Garage'))
  check('ambiguous name is not silently resolved', /Which one/i.test(ambiguous))

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
