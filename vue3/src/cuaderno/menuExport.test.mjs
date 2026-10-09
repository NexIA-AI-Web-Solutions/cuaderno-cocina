import test from 'node:test'
import assert from 'node:assert/strict'
import {existsSync} from 'node:fs'
const modulePath = new URL('./menuExport.mjs', import.meta.url)
const exporter = existsSync(modulePath) ? await import(modulePath) : {}
test('wrap preserves accents, long words and explicit blank lines without truncation', () => {
    assert.equal(typeof exporter.wrapText, 'function', 'real wrapping implementation is required')
    const lines = exporter.wrapText('Menú gástrico\n\n' + 'á'.repeat(30), 8, s => [...s].length)
    assert.deepEqual(lines.slice(0, 3), ['Menú', 'gástrico', ''])
    assert.equal(lines.slice(3).join(''), 'á'.repeat(30)); assert.ok(lines.every(s => s.length <= 8))
})
test('large rows continue across pages and all content survives in both orientations', () => {
    assert.equal(typeof exporter.layoutMenu, 'function', 'real pagination implementation is required')
    for (const orientation of ['portrait','landscape']) {
        const title = Array.from({length: 1000}, (_, i) => 'plato' + i).join(' ')
        const doc = {orientation, declaration: 'Declaración manual', diet: 'celiacos', diet_label: 'Celíacos', menus:[{name:'Menú de prueba', entries:[{from_date:'2026-10-09',meal_type:{name:'Almuerzo'},course_name:'Primero',recipe:{name:title},servings:'25',diet_status:'unknown'}]}]}
        const pages = exporter.layoutMenu(doc, s => s.length * 10)
        assert.ok(pages.length > 1); assert.ok(pages.every(p => p.lines.some(l => l.text.includes('Menú de prueba'))))
        for (let i=0;i<1000;i++) assert.ok(pages.some(p => p.lines.some(l => l.text.split(' ').includes('plato'+i))), 'missing word '+i)
        assert.ok(pages.every(p => p.lines.every(l => l.y < p.height - 30)))
        assert.match(pages.flatMap(p => p.lines).map(l => l.text).join(' '), /No declarado/)
    }
})
test('exports reject oversized input before canvas allocation', () => {
    assert.equal(typeof exporter.layoutMenu, 'function')
    assert.throws(() => exporter.layoutMenu({menus:[{name:'a',entries:new Array(101).fill({})}]}, s=>s.length), /100/)
})
test('PDF uses byte accurate xref, JPEG image streams and orientation specific A4 pages', () => {
    assert.equal(typeof exporter.encodeMenuPdf, 'function', 'downloadable PDF implementation is required')
    const jpeg = Uint8Array.from([255,216,255,217])
    const bytes = exporter.encodeMenuPdf([{jpeg,width:1123,height:794},{jpeg,width:1123,height:794}], 'landscape')
    const text = new TextDecoder('latin1').decode(bytes)
    assert.ok(text.startsWith('%PDF-1.4')); assert.match(text, /\/Count 2/); assert.match(text, /\/MediaBox \[0 0 841.89 595.28\]/); assert.match(text, /\/Filter \/DCTDecode/)
    const xrefAt = Number(text.match(/startxref\n(\d+)/)[1]); assert.equal(text.slice(xrefAt,xrefAt+4),'xref')
    const lines = text.slice(xrefAt).split('\n'); const count = Number(lines[1].split(' ')[1])
    for(let id=1; id<count; id++) {const offset=Number(lines[id+2].slice(0,10)); assert.ok(text.slice(offset).startsWith(id+' 0 obj'), 'xref object '+id)}
})
