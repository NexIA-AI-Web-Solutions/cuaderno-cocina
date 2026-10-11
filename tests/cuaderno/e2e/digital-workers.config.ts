import {defineConfig} from '@playwright/test'

// Mutating acceptance is restricted to the disposable worker preview runtime.
const baseURL = process.env.CUADERNO_WORKER_TEST_URL || 'http://127.0.0.1:18083'
const target = new URL(baseURL)
if (target.hostname !== '127.0.0.1' || target.port !== '18083' || target.protocol !== 'http:' || target.pathname !== '/') {
    throw new Error('Los tests de trabajadores solo pueden ejecutarse en el entorno aislado 127.0.0.1:18083.')
}
export default defineConfig({
    testDir: '.', testMatch: /digital-workers\.spec\.ts/,
    fullyParallel: false, workers: 1, retries: 0, timeout: 90_000,
    expect: {timeout: 12_000},
    outputDir: '../../../docs/cuaderno/evidence/digital-workers-20261011/browser',
    reporter: [['list'], ['json', {outputFile: '../../../docs/cuaderno/evidence/digital-workers-20261011/browser-results.json'}]],
    use: {baseURL, browserName: 'chromium', launchOptions: {executablePath: process.env.CUADERNO_WORKER_BROWSER_EXECUTABLE}, viewport: {width: 1440, height: 900}, locale: 'es-ES', timezoneId: 'Europe/Madrid', serviceWorkers: 'block', trace: 'retain-on-failure', screenshot: 'only-on-failure'},
})
