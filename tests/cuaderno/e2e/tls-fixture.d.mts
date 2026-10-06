import type {LaunchOptions} from '@playwright/test'
export function ciTlsLaunchOptions(engine: 'chromium' | 'firefox' | 'webkit', values?: NodeJS.ProcessEnv): LaunchOptions
