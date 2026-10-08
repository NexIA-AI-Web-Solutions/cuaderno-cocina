import {defineConfig} from '@playwright/test'
import path from 'node:path'
import baseConfig from './playwright.config.js'
import {parseProject} from './contracts.js'

const output = process.env.CUADERNO_QUANTITY_RUN_DIR
if (!output || !path.isAbsolute(output)) throw new Error('CUADERNO_QUANTITY_RUN_DIR debe ser absoluta.')

// Keep the existing identity parser and TLS/auth contracts; each case changes
// its real viewport four times, including 1024 absent from the standard matrix.
const projects = (baseConfig.projects || []).filter(project => {
  const identity = parseProject(project.name || '')
  return identity.browser === 'chromium' && identity.width === 1440
}).map(project => ({...project, testMatch: /ingredient-quantity-precision\.spec\.ts$/, testIgnore: []}))
if (projects.length !== 9) throw new Error('La campaña requiere nueve proyectos Chromium de edición/rol.')

export default defineConfig({
  ...baseConfig,
  testMatch: /ingredient-quantity-precision\.spec\.ts$/,
  testIgnore: [],
  projects,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  outputDir: path.join(output, 'failure-diagnostics'),
  reporter: [['line'], ['json', {outputFile: path.join(output, 'playwright-results.json')}]],
  // Synthetic fixture screenshots are written explicitly. Browser storage and
  // traces can contain session cookies and must never enter this artifact.
  use: {...baseConfig.use, trace: 'off', video: 'off', screenshot: 'off', ignoreHTTPSErrors: false},
})
