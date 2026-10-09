import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const dataUrl=source=>`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const django=dataUrl(`export const resolveDjangoUrl=path=>path;export const csrfHeadersForUrl=()=>({'X-CSRFToken':'test-token'})`)
const apiStub=dataUrl(`export const cuadernoFetch=(...args)=>fetch(...args)`)
const apiSource=ts.transpileModule(readFileSync(new URL('./planningApi.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replaceAll("'@/cuaderno/api'",JSON.stringify(apiStub)).replaceAll("'@/utils/djangoConfig'",JSON.stringify(django))
const {uploadEntityImage,planningErrorMessage}=await import(dataUrl(apiSource))
const browserSource=ts.transpileModule(readFileSync(new URL('./menuExportBrowser.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replaceAll("'./menuExport.mjs'",JSON.stringify(new URL('./menuExport.mjs',import.meta.url).href)).replaceAll("'@/utils/djangoConfig'",JSON.stringify(django))
const {authorizedCoverUrl,imageDimensions,downloadMenu}=await import(dataUrl(browserSource))
test('multipart image save preserves CSRF and browser boundary and reports server field errors',async()=>{
    const original=globalThis.fetch
    const file=new File(['png'],'example.png',{type:'image/png'})
    try{
        globalThis.fetch=async(url,options)=>{
            assert.equal(url,'/api/cuaderno/foods/3/image/');assert.equal(options.method,'PUT');assert.equal(options.credentials,'same-origin');assert.equal(options.redirect,'error');assert.equal(options.headers['X-CSRFToken'],'test-token');assert.equal(options.headers['Content-Type'],undefined)
            assert.equal(options.body.get('image').name,'example.png');assert.equal(options.body.get('caption'),'Tomate español')
            return new Response(JSON.stringify({image:['La imagen está dañada.']}),{status:400})
        }
        await assert.rejects(uploadEntityImage('foods/3/image/',file,'Tomate español'),/Imagen: La imagen está dañada/)
        assert.equal(planningErrorMessage({caption:['Descripción demasiado larga.']},'fallback'),'Descripción: Descripción demasiado larga.')
    }finally{globalThis.fetch=original}
})
test('invalid MIME, over 5 MiB and arbitrary destinations are rejected before network requests',async()=>{
    const original=globalThis.fetch;let calls=0;globalThis.fetch=async()=>{calls++;throw new Error('Unexpected fetch')}
    try{
        await assert.rejects(uploadEntityImage('foods/3/image/',new File(['svg'],'a.svg',{type:'image/svg+xml'}),''),/JPG/)
        await assert.rejects(uploadEntityImage('foods/3/image/',new File([new Uint8Array(5*1024*1024+1)],'a.png',{type:'image/png'}),''),/5 MiB/)
        await assert.rejects(uploadEntityImage('https://other.test/',new File(['png'],'a.png',{type:'image/png'}),''),/destino/)
        assert.equal(calls,0)
    }finally{globalThis.fetch=original}
})
test('cover URL permits only authorized same-origin template content and dimensions are read before decode',()=>{
    const original=globalThis.window;globalThis.window={location:{origin:'https://cuaderno.test'}}
    try{
        assert.equal(authorizedCoverUrl('/api/cuaderno/planning/templates/3/image/content/'),'https://cuaderno.test/api/cuaderno/planning/templates/3/image/content/')
        const contentPath='/api/cuaderno/planning/templates/3/image/content/'
        assert.equal(authorizedCoverUrl(contentPath+'?v=0123456789abcdef'),'https://cuaderno.test'+contentPath+'?v=0123456789abcdef')
        for(const url of ['https://other.test'+contentPath+'?v=0123456789abcdef','/arbitrary.jpg','/wrong-prefix'+contentPath+'?v=0123456789abcdef',contentPath+'?next=x',contentPath+'?v=0123456789abcdef&next=x',contentPath+'?v=0123456789abcdef&v=0123456789abcdef',contentPath+'?v=0123456789ABCDEf',contentPath+'?v=0123456789abcde',contentPath+'?v=0123456789abcdef0',contentPath+'?v=',contentPath+'?v=0123456789abcdef#image']) assert.throws(()=>authorizedCoverUrl(url),/autorizada/)
        const png=new Uint8Array(24);png[0]=137;png[1]=80;const view=new DataView(png.buffer);view.setUint32(16,1200);view.setUint32(20,800);assert.deepEqual(imageDimensions(png),[1200,800])
        assert.throws(()=>imageDimensions(new Uint8Array(2)),/leer la portada/)
    }finally{globalThis.window=original}
})

test('PNG and PDF render at twice the logical A4 pixels and PDF declares physical image dimensions', async () => {
    const originals={document:globalThis.document,setTimeout:globalThis.setTimeout,create:URL.createObjectURL,revoke:URL.revokeObjectURL}
    const renders=[],scales=[],downloads=[]
    globalThis.setTimeout=callback=>{callback(); return 0}
    URL.createObjectURL=blob=>{downloads.push(blob);return 'blob:download'};URL.revokeObjectURL=()=>{}
    const context={font:'',measureText:text=>({width:text.length*10}),scale:(x,y)=>scales.push([x,y]),fillRect(){},fillText(){},drawImage(){}}
    globalThis.document={fonts:{ready:Promise.resolve()},body:{append(){}},createElement:kind=>kind==='canvas'?{width:0,height:0,getContext:()=>context,toBlob(callback,type){renders.push({width:this.width,height:this.height,type});callback(new Blob([new Uint8Array([255,216,255,217])],{type}))}}:{click(){},remove(){}}}
    try {
        const document={orientation:'portrait',menus:[{name:'Menú',entries:[]}],declaration:'Manual',diet:null,diet_label:null,merged:false}
        await downloadMenu(document,'png');await downloadMenu({...document,orientation:'landscape'},'pdf')
        assert.deepEqual(renders,[{width:1588,height:2246,type:'image/png'},{width:2246,height:1588,type:'image/jpeg'}])
        assert.deepEqual(scales,[[2,2],[2,2]])
        const pdf=await downloads[1].text();assert.match(pdf,/\/Width 2246 \/Height 1588/);assert.match(pdf,/\/MediaBox \[0 0 841.89 595.28\]/)
    } finally {globalThis.document=originals.document;globalThis.setTimeout=originals.setTimeout;URL.createObjectURL=originals.create;URL.revokeObjectURL=originals.revoke}
})
