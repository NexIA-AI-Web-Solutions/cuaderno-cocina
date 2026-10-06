import test from 'node:test'
import assert from 'node:assert/strict'
import {loadTestModule as load} from './testModuleLoader.mjs'
const configModule = '../utils/djangoConfig.ts'
let config = {
    csrfCookieName: 'cuaderno_csrftoken', languageCookieName: 'cuaderno_language',
    languageCookiePath: '/cuaderno-cocina/', languageCookieSecure: true,
    mediaUrl: '/cuaderno-cocina/media/',
}
globalThis.document = {
    baseURI: 'https://example.test/cuaderno-cocina/',
    cookie: 'csrftoken=foreign; cuaderno_csrftoken=our%2Btoken',
    getElementById: id => id === 'django_config' ? {textContent: JSON.stringify(config)} : null,
}
globalThis.window = {location: {origin: 'https://example.test'}}

test('application resolver preserves URL components and does not duplicate its prefix', async () => {
    const {resolveDjangoUrl} = await import(await load(configModule))
    for (const source of ['/api/cuaderno/packages/?limit=2#part', 'api/cuaderno/packages/?limit=2#part', '/cuaderno-cocina/api/cuaderno/packages/?limit=2#part']) {
        assert.equal(resolveDjangoUrl(source), '/cuaderno-cocina/api/cuaderno/packages/?limit=2#part')
    }
    for (const source of ['https://other.test/api/x?q=1#f', '//other.test/api/x', 'https://example.test/api/x?q=1', 'data:text/plain,hello']) {
        assert.equal(resolveDjangoUrl(source), source)
    }
    assert.equal(resolveDjangoUrl('/api/x?q=1#f', true), '/cuaderno-cocina/api/x/?q=1#f')
})

test('CSRF uses configured cookie and contains tokens within the application', async () => {
    const {csrfHeadersForUrl} = await import(await load(configModule))
    assert.equal(csrfHeadersForUrl('/cuaderno-cocina/api/x')['X-CSRFToken'], 'our+token')
    for (const source of ['https://other.test/cuaderno-cocina/api/x', '//other.test/cuaderno-cocina/api/x', '/api/x', '/cuaderno-cocina-other/api/x', '/cuaderno-cocina/../api/x']) {
        assert.deepEqual(csrfHeadersForUrl(source), {})
    }
})

test('language cookie uses configured name and path with Secure and escaped value', async () => {
    const {setDjangoLanguage} = await import(await load(configModule))
    const previous = document.cookie
    setDjangoLanguage('es;bad', new Date('2030-01-01T00:00:00Z'))
    assert.equal(document.cookie, 'cuaderno_language=es%3Bbad; expires=Tue, 01 Jan 2030 00:00:00 GMT; path=/cuaderno-cocina/; SameSite=Lax; Secure')
    document.cookie = previous
})

test('cuaderno fetch prefixes endpoints and keeps configured CSRF out of external requests', async () => {
    const {cuadernoFetch} = await import(await load('./api.ts'))
    const previousFetch = globalThis.fetch
    const requests = []
    globalThis.fetch = async (url, options) => {
        requests.push({url, options})
        return new Response('{}')
    }
    try {
        await cuadernoFetch('/api/cuaderno/packages/?limit=2#f', {method: 'POST', body: '{}'})
        assert.equal(requests[0].url, '/cuaderno-cocina/api/cuaderno/packages/?limit=2#f')
        assert.equal(requests[0].options.headers.get('X-CSRFToken'), 'our+token')
        assert.equal(requests[0].options.redirect, 'error')
        await cuadernoFetch('https://third.test/api/x', {headers: {'X-CSRFToken': 'explicit'}})
        assert.equal(requests[1].options.headers.has('X-CSRFToken'), false)
        assert.equal(requests[1].options.credentials, 'same-origin')
    } finally {
        globalThis.fetch = previousFetch
    }
})

test('shared media tokens apply only to the configured same-origin media root', async () => {
    const {sharedMediaUrl} = await import(await load('./sharedMedia.ts'))
    assert.equal(sharedMediaUrl('/cuaderno-cocina/media/a.jpg?size=2#image', 'a+b', window.location.origin), '/cuaderno-cocina/media/a.jpg?size=2&share=a%2Bb#image')
    for (const source of ['/media/a.jpg', '/cuaderno-cocina/media-other/a.jpg', '/cuaderno-cocina/media/../api/x', 'https://third.test/cuaderno-cocina/media/a.jpg']) {
        assert.equal(sharedMediaUrl(source, 'secret', window.location.origin), source)
    }
    config.mediaUrl = 'https://bucket.test/media/'
    assert.equal(sharedMediaUrl('https://bucket.test/media/a.jpg', 'secret', window.location.origin), 'https://bucket.test/media/a.jpg')
    config.mediaUrl = '/media/'
    assert.equal(sharedMediaUrl('/media/a.jpg', 'secret', window.location.origin), '/media/a.jpg')
    config.mediaUrl = '/cuaderno-cocina/media/'
})

test('root and alternate-prefix installations derive URLs and fallback configuration from base', async () => {
    const {resolveDjangoUrl, getDjangoConfig} = await import(await load(configModule))
    const previousBase = document.baseURI, previousConfig = config
    try {
        config = {}
        document.baseURI = 'https://example.test/'
        assert.equal(resolveDjangoUrl('/api/recipe/?q=1'), '/api/recipe/?q=1')
        assert.equal(getDjangoConfig().csrfCookieName, 'csrftoken')
        assert.equal(getDjangoConfig().mediaUrl, '/media/')
        document.baseURI = 'https://example.test/other-kitchen/'
        assert.equal(resolveDjangoUrl('/api/recipe/?q=1'), '/other-kitchen/api/recipe/?q=1')
        assert.equal(getDjangoConfig().languageCookiePath, '/other-kitchen/')
    } finally {
        document.baseURI = previousBase
        config = previousConfig
    }
})

test('an external base cannot redirect application URLs or credentials', async () => {
    const {resolveDjangoUrl} = await import(await load(configModule))
    const previous = document.baseURI
    try {
        document.baseURI = 'https://third.test/cuaderno-cocina/'
        assert.throws(() => resolveDjangoUrl('/api/recipe/'), /origin/)
    } finally {
        document.baseURI = previous
    }
})

test('OpenAPI transport contains CSRF after a middleware URL change', async () => {
    const {BaseAPI, Configuration} = await import(await load('../openapi/runtime.ts'))
    const requests = []
    const api = new BaseAPI(new Configuration({fetchApi: async (url, options) => {
        requests.push({url, options})
        return new Response('{}')
    }}))
    await api.request({path: '/api/recipe/', method: 'POST', headers: {}, body: {}})
    assert.equal(requests[0].url, '/cuaderno-cocina/api/recipe/')
    assert.equal(new Headers(requests[0].options.headers).get('X-CSRFToken'), 'our+token')
    assert.equal(requests[0].options.redirect, 'error')
    const external = api.withPreMiddleware(params => ({...params, url: 'https://third.test/api/x'}))
    await external.request({path: '/api/recipe/', method: 'POST', headers: {}, body: {}})
    assert.equal(new Headers(requests[1].options.headers).has('X-CSRFToken'), false)
})

test('both image upload entry points use the prefixed endpoint and configured cookie', async () => {
    const {useFileApi} = await import(await load('../composables/useFileApi.ts'))
    const {uploadRecipeImage} = await import(await load('../utils/utils.ts'))
    const previousFetch = globalThis.fetch
    const requests = []
    globalThis.fetch = async (url, options) => {
        requests.push({url, options})
        return new Response('{}')
    }
    try {
        await useFileApi().updateRecipeImage(42, null)
        await uploadRecipeImage(42, new File(['image'], 'image.png', {type: 'image/png'}))
        assert.equal(requests.length, 2)
        for (const {url, options} of requests) {
            assert.equal(url, '/cuaderno-cocina/api/recipe/42/image/')
            assert.equal(new Headers(options.headers).get('X-CSRFToken'), 'our+token')
            assert.equal(options.redirect, 'error')
            assert.equal(options.body instanceof FormData, true)
        }
    } finally {
        globalThis.fetch = previousFetch
    }
})
