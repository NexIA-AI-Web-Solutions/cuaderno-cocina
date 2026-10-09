import {defineConfig, devices, type Project} from '@playwright/test'
import {authFile, editions, projectName, roles, widths} from './contracts.js'
import {ciTlsLaunchOptions} from './tls-fixture.mjs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:18081'
const outputDir = process.env.CUADERNO_E2E_OUTPUT_DIR || 'test-results'
const htmlReportDir = process.env.CUADERNO_E2E_HTML_REPORT || 'playwright-report'
const prefixAcceptance = process.env.CUADERNO_E2E_PREFIX === '1'
const chromiumLaunchOptions = ciTlsLaunchOptions('chromium')

const projects: Project[] = editions.flatMap(edition => roles.flatMap(role => widths.map(width => ({
  name: projectName(edition, role, width),
  testIgnore: prefixAcceptance ? /(?:browser-acceptance|ingredient-quantity-precision)\.spec\.ts/ : /(?:browser-acceptance|prefix-acceptance|ingredient-quantity-precision)\.spec\.ts/,
  use: {
    ...devices['Desktop Chrome'],
    launchOptions: chromiumLaunchOptions,
    baseURL,
    viewport: {width, height: width === 390 ? 844 : width === 768 ? 1024 : 900},
    storageState: authFile(edition, role),
  },
}))))

// Keep the full edition/role/viewport matrix on Chromium. These two focused
// projects catch engine-specific layout, keyboard and print-CSS regressions
// without tripling the state-mutating acceptance suite.
projects.push(
  {
    name: projectName('esencial', 'responsable', 390, 'firefox'),
    testMatch: prefixAcceptance ? /(?:browser-acceptance|prefix-acceptance|modernization-acceptance|functional-extensions-acceptance|menu-media-exports)\.spec\.ts/ : /(?:browser-acceptance|modernization-acceptance|functional-extensions-acceptance|menu-media-exports)\.spec\.ts/,
    use: {
      ...devices['Desktop Firefox'],
      launchOptions: ciTlsLaunchOptions('firefox'),
      baseURL,
      viewport: {width: 390, height: 844},
      storageState: authFile('esencial', 'responsable'),
    },
  },
  {
    name: projectName('integral', 'responsable', 768, 'webkit'),
    testMatch: prefixAcceptance ? /(?:browser-acceptance|prefix-acceptance|modernization-acceptance|functional-extensions-acceptance|menu-media-exports)\.spec\.ts/ : /(?:browser-acceptance|modernization-acceptance|functional-extensions-acceptance|menu-media-exports)\.spec\.ts/,
    use: {
      ...devices['Desktop Safari'],
      launchOptions: ciTlsLaunchOptions('webkit'),
      baseURL,
      viewport: {width: 768, height: 1024},
      storageState: authFile('integral', 'responsable'),
    },
  },
)

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  globalSetup: './global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  timeout: 45_000,
  expect: {timeout: 8_000},
  outputDir,
  reporter: process.env.CI ? [['line'], ['html', {open: 'never', outputFolder: htmlReportDir}]] : 'list',
  use: {
    baseURL,
    ignoreHTTPSErrors: process.env.CUADERNO_E2E_SELF_SIGNED === '1',
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects,
})
