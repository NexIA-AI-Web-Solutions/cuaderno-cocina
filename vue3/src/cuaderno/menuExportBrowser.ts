import {layoutMenu, encodeMenuPdf, type ExportPage} from './menuExport.mjs'
import type {PrintedMenus} from './planningApi'
import {resolveDjangoUrl} from '@/utils/djangoConfig'

/** Read dimensions before decoding to bound memory even for compressed images. */
export function imageDimensions(bytes: Uint8Array): [number, number] {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    if (bytes.length >= 24 && bytes[0] === 137 && bytes[1] === 80) return [view.getUint32(16), view.getUint32(20)]
    if (bytes.length >= 10 && bytes[0] === 71 && bytes[1] === 73) return [view.getUint16(6,true),view.getUint16(8,true)]
    if (bytes.length >= 30 && String.fromCharCode(...bytes.slice(0,4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8,12)) === 'WEBP') {
        const kind=String.fromCharCode(...bytes.slice(12,16))
        if(kind==='VP8X') return [1+bytes[24]+bytes[25]*256+bytes[26]*65536,1+bytes[27]+bytes[28]*256+bytes[29]*65536]
        if(kind==='VP8 ') return [view.getUint16(26,true)&0x3fff,view.getUint16(28,true)&0x3fff]
        if(kind==='VP8L' && bytes[20]===47) return [1+(((bytes[22]&63)<<8)|bytes[21]),1+(((bytes[24]&15)<<10)|(bytes[23]<<2)|(bytes[22]>>6))]
    }
    if(bytes[0]===255 && bytes[1]===216) {
        let cursor=2
        while(cursor+9<bytes.length) {
            if(bytes[cursor++]!==255) break
            while(bytes[cursor]===255) cursor++
            const marker=bytes[cursor++]; if(marker===217 || marker===218) break
            if(marker===1 || (marker>=208 && marker<=215)) continue
            const length=view.getUint16(cursor)
            if(length<2 || cursor+length>bytes.length) break
            if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker)) return [view.getUint16(cursor+5),view.getUint16(cursor+3)]
            cursor+=length
        }
    }
    throw new Error('No se pudo leer la portada. Prueba con una imagen JPG, PNG, WebP o GIF válida.')
}
export function authorizedCoverUrl(path: string): string {
    const url=new URL(resolveDjangoUrl(path),window.location.origin)
    const queryEntries = [...url.searchParams.entries()]
    const validQuery = !url.search || (queryEntries.length === 1 && queryEntries[0][0] === 'v' && /^[a-f0-9]{16}$/.test(queryEntries[0][1]))
    const route = url.pathname.match(/\/api\/cuaderno\/planning\/templates\/(\d+)\/image\/content\/$/)
    const expectedPath = route ? new URL(resolveDjangoUrl(`/api/cuaderno/planning/templates/${route[1]}/image/content/`), window.location.origin).pathname : null
    if(url.origin!==window.location.origin || url.pathname !== expectedPath || !validQuery || url.hash) throw new Error('La portada debe proceder de una plantilla autorizada de Cuaderno Cocina.')
    return url.href
}
async function loadCover(path:string):Promise<ImageBitmap> {
    const response=await fetch(authorizedCoverUrl(path),{credentials:'same-origin',redirect:'error'})
    if(!response.ok) throw new Error('No se pudo cargar la portada. Actualiza el documento y comprueba tus permisos.')
    const length=Number(response.headers.get('content-length')||0)
    if(length>5*1024*1024) throw new Error('La portada supera 5 MiB.')
    // Bound the bytes while reading, including responses without Content-Length.
    const reader=response.body?.getReader(); if(!reader) throw new Error('No se pudo leer la portada.')
    const chunks:Uint8Array[]=[];let size=0
    try {while(true) {const {value,done}=await reader.read();if(done) break;size+=value.length;if(size>5*1024*1024) {await reader.cancel();throw new Error('La portada supera 5 MiB.')}chunks.push(value)}} finally {reader.releaseLock()}
    const bytes=new Uint8Array(size);let at=0;for(const chunk of chunks) {bytes.set(chunk,at);at+=chunk.length}
    const [width,height]=imageDimensions(bytes)
    if(!width || !height || width*height>16000000 || width>8192 || height>8192) throw new Error('La portada tiene demasiados píxeles. Reduce la imagen a un máximo de 16 megapíxeles y 8192 píxeles por lado.')
    const scale=Math.min(1,1000/Math.max(width,height))
    return createImageBitmap(new Blob([bytes]),{resizeWidth:Math.max(1,Math.round(width*scale)),resizeHeight:Math.max(1,Math.round(height*scale))})
}
const canvasBlob=(canvas:HTMLCanvasElement,type:string)=>new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('No se pudo generar el archivo. Prueba con menos platos.')),type,0.92))
function download(blob:Blob,name:string) {
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000)
}
function paint(canvas:HTMLCanvasElement,page:ExportPage,cover:ImageBitmap|null) {
    canvas.width=page.width*2;canvas.height=page.height*2
    const context=canvas.getContext('2d');if(!context) throw new Error('Este navegador no permite crear el documento.')
    context.scale(2,2)
    context.fillStyle='#ffffff';context.fillRect(0,0,page.width,page.height);context.textBaseline='top'
    if(cover) {const scale=Math.min((page.width-96)/cover.width,page.imageHeight/cover.height);context.drawImage(cover,48,page.imageY,cover.width*scale,cover.height*scale)}
    for(const line of page.lines) {
        context.font=line.kind==='title'?'bold 22px sans-serif':line.kind==='dish'||line.kind==='heading'?'bold 16px sans-serif':'16px sans-serif'
        context.fillStyle=line.unsuitable?'#8c1b1b':'#26352a';context.fillText(line.text,48,line.y)
    }
}
export async function downloadMenu(doc:PrintedMenus,format:'png'|'pdf',onPages:(count:number)=>void=()=>{}):Promise<number> {
    await document.fonts?.ready
    // Layout all text before allocating full-sized pages or decoding covers.
    const probe=document.createElement('canvas'),context=probe.getContext('2d');if(!context) throw new Error('Este navegador no permite exportar imágenes.')
    context.font='bold 22px sans-serif'
    const pages=layoutMenu(doc,text=>context.measureText(text).width);probe.width=probe.height=0;onPages(pages.length)
    const canvas=document.createElement('canvas'),pngs:Blob[]=[],pdfImages:{jpeg:Uint8Array;width:number;height:number}[]=[]
    let size=0
    try {
        for(const page of pages) {
            let cover:ImageBitmap|null=null
            try {if(page.image) cover=await loadCover(page.image.url);paint(canvas,page,cover)} finally {cover?.close()}
            const blob=await canvasBlob(canvas,format==='png'?'image/png':'image/jpeg');size+=blob.size
            if(size>40*1024*1024) throw new Error('Los archivos superan 40 MiB. Divide el documento antes de descargar.')
            if(format==='png') pngs.push(blob);else pdfImages.push({jpeg:new Uint8Array(await blob.arrayBuffer()),width:canvas.width,height:canvas.height})
            canvas.width=canvas.height=0
        }
        if(format==='pdf') download(new Blob([new Uint8Array(encodeMenuPdf(pdfImages,doc.orientation)).buffer],{type:'application/pdf'}),'menus.pdf')
        else for(let i=0;i<pngs.length;i++) download(pngs[i],`menus-pagina-${i+1}.png`)
        return pages.length
    } finally {canvas.width=canvas.height=0}
}
