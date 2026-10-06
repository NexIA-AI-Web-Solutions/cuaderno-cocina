import test from 'node:test'
import assert from 'node:assert/strict'
import {loadTestModule} from './testModuleLoader.mjs'
const {sharedMediaUrl} = await import(await loadTestModule('./sharedMedia.ts'))
const origin = 'https://cocina.example'
test('local media receives encoded share token while preserving query and fragment', () => {
    const result = new URL(sharedMediaUrl('/media/recipes/photo.jpg?size=40#image', 'a+b&c', origin), origin)
    assert.equal(result.searchParams.get('share'), 'a+b&c')
    assert.equal(result.searchParams.get('size'), '40')
    assert.equal(result.hash, '#image')
    assert.equal(new URL(sharedMediaUrl(`${origin}/media/file.pdf?share=old`, 'new', origin)).searchParams.get('share'), 'new')
})
test('external, S3, non-media and absent-token URLs are unchanged', () => {
    for (const url of ['https://bucket.s3.amazonaws.com/media/photo.jpg?X-Amz-Signature=abc', '//other.example/media/x', 'https://cocina.example.evil/media/x', '/api/recipe/1/', '/media-other/x', 'data:image/png;base64,abc', '/media/../api/x']) {
        assert.equal(sharedMediaUrl(url, 'secret', origin), url)
    }
    assert.equal(sharedMediaUrl('/media/x', undefined, origin), '/media/x')
    assert.equal(sharedMediaUrl(undefined, 'secret', origin), undefined)
})
