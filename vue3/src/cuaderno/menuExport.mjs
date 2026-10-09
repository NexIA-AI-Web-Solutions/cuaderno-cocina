// A4 at 96 dpi. Pure layout is shared by PNG and the JPEG-backed PDF renderer.
export const MAX_EXPORT_PAGES = 40
export function wrapText(value, width, measure) {
    const result = []
    for (const paragraph of String(value ?? '').split('\n')) {
        if (!paragraph.trim()) {result.push(''); continue}
        let line = ''
        for (const word of paragraph.trim().split(/\s+/u)) {
            if (measure(line ? line + ' ' + word : word) <= width) {line = line ? line + ' ' + word : word; continue}
            if (line) {result.push(line); line = ''}
            for (const character of word) {
                if (line && measure(line + character) > width) {result.push(line); line = ''}
                line += character
            }
        }
        if (line) result.push(line)
    }
    return result
}
export function layoutMenu(doc, measure) {
    if (!doc.menus?.length || doc.menus.length > 5 || doc.menus.some(m => m.entries.length > 100)) throw new Error('El documento admite hasta 5 menús y 100 platos por menú. Divide la selección.')
    if (JSON.stringify(doc).length > 200000) throw new Error('El documento contiene demasiado texto. Divide la selección en varios documentos.')
    const landscape = doc.orientation === 'landscape', width = landscape ? 1123 : 794, height = landscape ? 794 : 1123
    const pages = [], margin = 48, lineHeight = 25, usableWidth = width - margin * 2
    for (const menu of doc.menus) {
        let page, y
        const header = [...wrapText(menu.name, usableWidth, measure).map(text => ({text,kind:'title'})),
            ...wrapText(doc.declaration, usableWidth, measure).map(text => ({text,kind:'declaration'})),
            ...(doc.diet ? wrapText('Declaración consultada: ' + (doc.diet_label || doc.diet), usableWidth, measure).map(text=>({text,kind:'declaration'})) : []),
            {text:'Fecha · comida · tipo de plato · raciones',kind:'heading'}]
        if (header.length > 10) throw new Error('El título o la declaración es demasiado largo. Acórtalo antes de exportar.')
        const newPage = (first = false) => {
            if (pages.length >= MAX_EXPORT_PAGES) throw new Error('El documento supera 40 páginas. Divide la selección antes de descargar.')
            page = {width,height,lines:[],image:first ? menu.image : null,imageY:0,imageHeight:0}; pages.push(page); y=margin
            for(const line of header) {page.lines.push({...line,y}); y+=lineHeight}
            y += 14
            if (first && menu.image) {page.imageY=y; page.imageHeight=145; y+=160; for(const text of wrapText(menu.image.caption || '',usableWidth,measure)) {page.lines.push({text,y,kind:'declaration'}); y+=lineHeight}}
            if(y > height-100) throw new Error('La descripción de portada es demasiado larga. Acórtala antes de exportar.')
        }
        newPage(true)
        for (const entry of menu.entries) {
            const status = entry.diet_status === 'suitable' ? 'Apto · declaración manual' : entry.diet_status === 'unsuitable' ? 'No apto · declaración manual' : 'No declarado'
            const fields = [entry.from_date.slice(0,10) + (entry.to_date ? ' — ' + entry.to_date.slice(0,10) : '') + ' · ' + entry.meal_type.name + (entry.course_name ? ' · ' + entry.course_name : ''), entry.recipe?.name || entry.title || 'Plato sin receta', 'Raciones: ' + entry.servings, ...(doc.diet ? ['Declaración: ' + status] : [])]
            const lines = fields.flatMap((field,index) => wrapText(field,usableWidth,measure).map(text=>({text,kind:index === 1 ? 'dish' : 'body',unsuitable:doc.diet && entry.diet_status === 'unsuitable'})))
            if(y + Math.min(lines.length,5)*lineHeight > height-70) newPage()
            for(const line of lines) {if(y+lineHeight > height-70) newPage(); page.lines.push({...line,y});y+=lineHeight}
            y+=18
        }
    }
    for(let i=0;i<pages.length;i++) pages[i].lines.push({text:`Página ${i+1} de ${pages.length}`,y:pages[i].height-40,kind:'footer'})
    return pages
}
export function encodeMenuPdf(images, orientation) {
    if(!images.length || images.length > MAX_EXPORT_PAGES) throw new Error('Número de páginas no admitido.')
    const encoder = new TextEncoder(), chunks=[], offsets=[0]; let size=0
    const append = value => {const bytes=typeof value === 'string' ? encoder.encode(value) : value; chunks.push(bytes);size+=bytes.length}
    const object = (id,content,stream) => {offsets[id]=size;append(`${id} 0 obj\n${content}`);if(stream) {append('\nstream\n');append(stream);append('\nendstream')}append('\nendobj\n')}
    append('%PDF-1.4\n%Cuaderno Cocina\n')
    object(1,'<< /Type /Catalog /Pages 2 0 R >>')
    object(2,`<< /Type /Pages /Count ${images.length} /Kids [${images.map((_,i)=>`${3+i*3} 0 R`).join(' ')}] >>`)
    const [w,h] = orientation === 'landscape' ? [841.89,595.28] : [595.28,841.89]
    images.forEach((image,i)=>{
        const id=3+i*3, content=encoder.encode(`q\n${w} 0 0 ${h} 0 0 cm\n/Im0 Do\nQ\n`)
        object(id,`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im0 ${id+2} 0 R >> >> /Contents ${id+1} 0 R >>`)
        object(id+1,`<< /Length ${content.length} >>`,content)
        object(id+2,`<< /Type /XObject /Subtype /Image /Width ${image.width} /Height ${image.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${image.jpeg.length} >>`,image.jpeg)
    })
    const xref=size, count=3+images.length*3
    append(`xref\n0 ${count}\n0000000000 65535 f \n`)
    for(let id=1;id<count;id++) append(`${String(offsets[id]).padStart(10,'0')} 00000 n \n`)
    append(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`)
    const result = new Uint8Array(size);let cursor=0;for(const chunk of chunks) {result.set(chunk,cursor);cursor+=chunk.length}return result
}
