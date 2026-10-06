import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {createHash, X509Certificate} from 'node:crypto'
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
import test from 'node:test'
import {ciTlsLaunchOptions} from './tls-fixture.mjs'

const directory = mkdtempSync(path.join(tmpdir(), 'cuaderno-ci-tls-test-'))
const certPath = path.join(directory, 'fixture.crt')
const policyPath = path.join(directory, 'policies.json')
const wrongPath = path.join(directory, 'other.crt')
function certificate(destination, san) {
  const result = spawnSync('openssl', ['req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
    '-nodes', '-days', '1', '-subj', '/CN=Cuaderno CI fixture', '-addext', 'basicConstraints=critical,CA:TRUE',
    '-addext', 'keyUsage=critical,digitalSignature,keyCertSign', '-addext', 'extendedKeyUsage=serverAuth',
    '-addext', `subjectAltName=${san}`, '-keyout', destination + '.key', '-out', destination], {encoding: 'utf8'})
  assert.equal(result.status, 0, 'Synthetic test certificate generation failed.')
}
certificate(certPath, 'IP:127.0.0.1')
certificate(wrongPath, 'DNS:foreign.invalid')
writeFileSync(policyPath, JSON.stringify({policies: {Certificates: {Install: [certPath]}}}))
test.after(() => rmSync(directory, {recursive: true, force: true}))
const values = {CI: '1', CUADERNO_ENV: 'test', CUADERNO_E2E_PREFIX: '1', CUADERNO_E2E_SELF_SIGNED: '0',
  BASE_URL: 'https://127.0.0.1:18443/cuaderno-cocina/', CUADERNO_E2E_TLS_CERT: certPath,
  CUADERNO_E2E_TLS_CA: certPath, NODE_EXTRA_CA_CERTS: certPath, PLAYWRIGHT_FIREFOX_POLICIES_JSON: policyPath}

test('root projects retain ordinary browser certificate verification and launch defaults', () => {
  for (const engine of ['chromium', 'firefox', 'webkit']) assert.deepEqual(ciTlsLaunchOptions(engine, {}), {})
})

test('Chromium trusts only the exact generated server public key', () => {
  const certificate = new X509Certificate(readFileSync(certPath))
  const pin = createHash('sha256').update(certificate.publicKey.export({type: 'spki', format: 'der'})).digest('base64')
  assert.deepEqual(ciTlsLaunchOptions('chromium', values), {args: [`--ignore-certificate-errors-spki-list=${pin}`]})
})

test('Firefox and WebKit use generated CA trust without certificate-error bypass flags', () => {
  for (const engine of ['firefox', 'webkit']) assert.deepEqual(ciTlsLaunchOptions(engine, values), {})
})

test('fixture trust requires isolated CI and an exact HTTPS loopback prefix', () => {
  for (const changes of [{CI: ''}, {CUADERNO_ENV: 'production'}, {BASE_URL: 'https://foreign.invalid/cuaderno-cocina/'},
    {BASE_URL: 'http://127.0.0.1:18443/cuaderno-cocina/'}, {BASE_URL: 'https://127.0.0.1:18443/'}]) {
    assert.throws(() => ciTlsLaunchOptions('chromium', {...values, ...changes}), /CI|loopback|prefijo/)
  }
})

test('missing trust material and blanket HTTPS ignoring fail before any browser is launched', () => {
  for (const name of ['CUADERNO_E2E_TLS_CERT', 'CUADERNO_E2E_TLS_CA', 'NODE_EXTRA_CA_CERTS', 'PLAYWRIGHT_FIREFOX_POLICIES_JSON']) {
    assert.throws(() => ciTlsLaunchOptions('chromium', {...values, [name]: ''}), /TLS|CA|Firefox/)
  }
  assert.throws(() => ciTlsLaunchOptions('chromium', {...values, CUADERNO_E2E_SELF_SIGNED: '1'}), /ignorar|TLS/)
})

test('wrong SAN, wrong CA and mismatched Node trust are rejected', () => {
  for (const changes of [{CUADERNO_E2E_TLS_CERT: wrongPath}, {CUADERNO_E2E_TLS_CA: wrongPath}, {NODE_EXTRA_CA_CERTS: wrongPath}]) {
    assert.throws(() => ciTlsLaunchOptions('chromium', {...values, ...changes}), /TLS|CA/)
  }
})

test('Firefox policy must install exactly the generated CA', () => {
  const otherPolicy = path.join(directory, 'foreign-policies.json')
  for (const installed of [[wrongPath], [certPath, wrongPath]]) {
    writeFileSync(otherPolicy, JSON.stringify({policies: {Certificates: {Install: installed}}}))
    assert.throws(() => ciTlsLaunchOptions('firefox', {...values, PLAYWRIGHT_FIREFOX_POLICIES_JSON: otherPolicy}), /Firefox/)
  }
})

test('expired fixture certificates and ambiguous certificate bundles fail closed', t => {
  const now = Date.now()
  t.mock.method(Date, 'now', () => now + 3 * 24 * 60 * 60 * 1000)
  assert.throws(() => ciTlsLaunchOptions('chromium', values), /TLS\/CA/)
  t.mock.restoreAll()
  const bundle = path.join(directory, 'ambiguous.pem')
  writeFileSync(bundle, readFileSync(certPath, 'utf8') + readFileSync(wrongPath, 'utf8'))
  assert.throws(() => ciTlsLaunchOptions('chromium', {...values, CUADERNO_E2E_TLS_CERT: bundle}), /TLS\/CA/)
})
