import {createHash, X509Certificate} from 'node:crypto'
import {readFileSync, realpathSync, statSync} from 'node:fs'
import path from 'node:path'

function trustFile(name, values) {
  const filename = values[name]
  if (!filename || !path.isAbsolute(filename)) throw new Error(`Falta el archivo TLS/CA de CI: ${name}.`)
  try {
    const resolved = realpathSync(filename)
    if (!statSync(resolved).isFile()) throw new Error()
    return resolved
  } catch {
    throw new Error(`No se puede leer el archivo TLS/CA de CI: ${name}.`)
  }
}

function certificate(filename) {
  try {
    const pem = readFileSync(filename, 'utf8')
    if ((pem.match(/-----BEGIN CERTIFICATE-----/g) || []).length !== 1 || pem.includes('PRIVATE KEY')) throw new Error()
    const result = new X509Certificate(pem)
    const now = Date.now()
    if (!(Date.parse(result.validFrom) <= now && now < Date.parse(result.validTo))) throw new Error()
    return result
  } catch {
    throw new Error('El certificado TLS/CA efímero de CI no es válido.')
  }
}

/** Trust only the generated fixture; production and root runs keep browser defaults. */
export function ciTlsLaunchOptions(engine, values = process.env) {
  if (!['chromium', 'firefox', 'webkit'].includes(engine)) throw new Error('Motor de navegador desconocido.')
  if (values.CUADERNO_E2E_PREFIX !== '1') return {}
  if (!['1', 'true'].includes(values.CI) || values.CUADERNO_ENV !== 'test') {
    throw new Error('La confianza TLS de la fixture se limita al CI aislado de test.')
  }
  const target = new URL(values.BASE_URL)
  if (target.protocol !== 'https:' || target.hostname !== '127.0.0.1' || !target.port ||
      target.pathname !== '/cuaderno-cocina/' || target.username || target.password || target.search || target.hash) {
    throw new Error('La fixture TLS requiere HTTPS loopback con el prefijo exacto.')
  }
  if (values.CUADERNO_E2E_SELF_SIGNED === '1') {
    throw new Error('La fixture TLS usa confianza específica; no se permite ignorar errores HTTPS.')
  }
  const leafPath = trustFile('CUADERNO_E2E_TLS_CERT', values)
  const caPath = trustFile('CUADERNO_E2E_TLS_CA', values)
  const leaf = certificate(leafPath)
  const ca = certificate(caPath)
  if (leaf.checkIP(target.hostname) !== target.hostname || !ca.ca || !ca.verify(ca.publicKey) || !leaf.verify(ca.publicKey)) {
    throw new Error('El certificado TLS no coincide con loopback o con la CA generada.')
  }
  if (trustFile('NODE_EXTRA_CA_CERTS', values) !== caPath) throw new Error('La CA de Node no coincide con la fixture TLS.')
  const policyPath = trustFile('PLAYWRIGHT_FIREFOX_POLICIES_JSON', values)
  try {
    const policy = JSON.parse(readFileSync(policyPath, 'utf8'))
    const installed = policy.policies.Certificates.Install
    if (Object.keys(policy.policies).join() !== 'Certificates' ||
        Object.keys(policy.policies.Certificates).join() !== 'Install' ||
        !Array.isArray(installed) || installed.length !== 1 || !path.isAbsolute(installed[0]) ||
        realpathSync(installed[0]) !== caPath) throw new Error()
  } catch {
    throw new Error('La política de Firefox debe instalar únicamente la CA generada.')
  }
  // Chromium's network-service certificate verifier also covers SW script fetches.
  // Playwright's per-page ignoreHTTPSErrors cannot establish that worker trust.
  if (engine === 'chromium') {
    const pin = createHash('sha256').update(leaf.publicKey.export({type: 'spki', format: 'der'})).digest('base64')
    return {args: [`--ignore-certificate-errors-spki-list=${pin}`]}
  }
  // Firefox inherits PLAYWRIGHT_FIREFOX_POLICIES_JSON. WebKit's bundled launcher
  // uses the OS CA bundle populated only on the disposable CI runner.
  return {}
}
