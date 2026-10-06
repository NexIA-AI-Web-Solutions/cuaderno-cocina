#!/usr/bin/env node
import assert from 'node:assert/strict'
import path from 'node:path'
import {pathToFileURL} from 'node:url'
import {ciTlsLaunchOptions} from './tls-fixture.mjs'

export function assertWorkerProof(proof, baseURL) {
  const target = new URL(baseURL)
  const script = new URL('service-worker.js', target).href
  const namespace = `cuaderno-${encodeURIComponent(target.pathname)}-`
  assert.equal(proof.secure, true, 'La fixture debe ser un contexto seguro.')
  assert.equal(proof.controller, script, 'El controller debe usar el worker canónico.')
  assert.equal(proof.state, 'activated', 'El worker debe terminar su activación.')
  assert.deepEqual(proof.scopes, [target.href], 'El worker debe controlar únicamente el prefijo exacto.')
  assert.ok(Object.keys(proof.caches).length > 0, 'El worker debe crear caches públicos propios.')
  let entries = 0
  for (const [name, sources] of Object.entries(proof.caches)) {
    assert.ok(name.startsWith(namespace), 'Un cache no pertenece al namespace de Cuaderno.')
    for (const source of sources) {
      const url = new URL(source)
      assert.equal(url.origin, target.origin, 'Un cache contiene assets de otro origen.')
      assert.ok(url.pathname.startsWith(target.pathname + 'static/'), 'Un cache contiene datos fuera de static del prefijo.')
      assert.equal(url.searchParams.has('share'), false, 'Un cache contiene una capacidad de media privada.')
      entries += 1
    }
  }
  assert.ok(entries > 0, 'El precache debe contener assets públicos reales.')
  return {cache_count: Object.keys(proof.caches).length, public_asset_count: entries}
}

async function enginePreflight(engine, browserType, values) {
  const started = Date.now()
  let browser
  let browserServer
  let timer
  const failures = []
  try {
    const probe = async () => {
      // Own a BrowserServer so a stuck graceful close can kill only this probe's
      // exact process. Its automation endpoint binds only runner loopback.
      browserServer = await browserType.launchServer({...ciTlsLaunchOptions(engine, values),
        env: {...process.env, ...values}, host: '127.0.0.1', timeout: 10_000})
      browser = await browserType.connect(browserServer.wsEndpoint(), {timeout: 10_000})
      const context = await browser.newContext({ignoreHTTPSErrors: false, storageState: {cookies: [], origins: []}})
      assert.deepEqual(await context.cookies(), [], 'La prueba TLS debe comenzar sin autenticación.')
      const page = await context.newPage()
      page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
      page.on('console', message => {
        if (message.type() === 'error') failures.push(`console: ${message.text()}`)
      })
      context.on('requestfailed', request => failures.push(`network: ${request.failure()?.errorText || 'fallo desconocido'}`))
      context.on('request', request => {
        const url = new URL(request.url())
        const target = new URL(values.BASE_URL)
        if (['https:', 'http:'].includes(url.protocol) &&
            (url.origin !== target.origin || !url.pathname.startsWith(target.pathname))) failures.push('Petición fuera del origen o prefijo.')
      })
      context.on('response', response => {
        if (response.status() >= 500) failures.push(`http ${response.status()}`)
      })
      const response = await page.goto(new URL('accounts/login/', values.BASE_URL).href, {waitUntil: 'domcontentloaded', timeout: 10_000})
      assert.equal(response?.status(), 200, 'El login público debe responder HTTPS 200.')
      await page.evaluate(async scope => {
        if (!window.isSecureContext) throw new Error('El origen TLS no es seguro.')
        const registration = await navigator.serviceWorker.register(new URL('service-worker.js', scope).href, {scope})
        if (registration.scope !== scope) throw new Error('El registro no conserva el scope exacto.')
      }, values.BASE_URL)
      await page.waitForFunction(scope => navigator.serviceWorker.controller?.scriptURL === new URL('service-worker.js', scope).href &&
        navigator.serviceWorker.controller?.state === 'activated',
        values.BASE_URL, {timeout: Math.max(1, 39_000 - (Date.now() - started))})
      const proof = await page.evaluate(async () => {
        const cachesSnapshot = {}
        for (const name of await caches.keys()) cachesSnapshot[name] = (await (await caches.open(name)).keys()).map(request => request.url)
        return {secure: window.isSecureContext, controller: navigator.serviceWorker.controller?.scriptURL,
          state: navigator.serviceWorker.controller?.state,
          scopes: (await navigator.serviceWorker.getRegistrations()).map(registration => registration.scope), caches: cachesSnapshot}
      })
      const counts = assertWorkerProof(proof, values.BASE_URL)
      assert.deepEqual(failures, [], 'El preflight TLS no admite errores de consola, red o prefijo.')
      return {engine, browser: browser.version(), passed: true, ...counts}
    }
    // Reserve five seconds of the existing 45-second engine budget for cleanup.
    return await Promise.race([probe(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timeout TLS preflight: ${engine}.`)), 40_000)
    })])
  } finally {
    clearTimeout(timer)
    let closeTimer
    try {
      await Promise.race([(async () => {
        if (browser) await browser.close()
        if (browserServer) await browserServer.close()
      })(), new Promise((_, reject) => {
        closeTimer = setTimeout(() => reject(new Error(`Timeout al cerrar el browser propio: ${engine}.`)), 5_000)
      })])
    } catch (error) {
      if (browserServer) await browserServer.kill()
      throw error
    } finally {
      clearTimeout(closeTimer)
    }
  }
}

export async function runPreflight(values = process.env) {
  if (values.CUADERNO_E2E_PREFIX !== '1') throw new Error('El preflight TLS requiere la fixture CI bajo prefijo.')
  // Validate the contract before importing or launching any browser.
  for (const engine of ['chromium', 'firefox', 'webkit']) ciTlsLaunchOptions(engine, values)
  const {chromium, firefox, webkit} = await import('@playwright/test')
  const results = []
  for (const [engine, browserType] of Object.entries({chromium, firefox, webkit})) {
    try {
      results.push(await enginePreflight(engine, browserType, values))
    } catch (error) {
      results.push({engine, passed: false, error: error.message})
    }
  }
  return {passed: results.every(result => result.passed), engines: results}
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const result = await runPreflight()
    process.stdout.write(JSON.stringify(result) + '\n')
    if (!result.passed) process.exitCode = 1
  } catch (error) {
    process.stderr.write(`TLS preflight failed: ${error.message}\n`)
    process.exitCode = 1
  }
}
