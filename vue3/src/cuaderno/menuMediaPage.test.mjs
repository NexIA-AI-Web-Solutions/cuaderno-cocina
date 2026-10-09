import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileStyle} from '@vue/compiler-sfc'
import {mountFunctional,button,field,textOf,flush} from './functionalComponentHarness.mjs'
const meal={id:7,title:'Sopa gástrica',recipe:null,meal_type:{id:1,name:'Almuerzo'},course:null,servings:'4',from_date:'2026-10-09T12:00:00Z',to_date:null,note:'',diet_status:'unknown'}
const data={courses:[],meal_plans:[meal],events:[],can_edit:true,can_manage_absences:false,can_merge_print:false}
test('a saved template survives rejected cover and retry never creates a duplicate',async()=>{
    let posts=0,rejected=true
    const saved={id:2,name:'Semana',weeks:1,revision:'a',entries:[]},file=new File([new Uint8Array(100)],'cover.png',{type:'image/png'})
    const mounted=await mountFunctional('./pages/MenuPlanningPage.vue',{},(path,method)=>{
        if(path==='edition/') return {edition:'profesional'}
        if(path.startsWith('planning/?')) return data
        if(path==='planning/templates/?offset=0&limit=50') return {count:posts,results:posts?[saved]:[]}
        if(path==='planning/templates/' && method==='POST') {posts++;return saved}
        assert.equal(path,'planning/templates/2/image/');assert.equal(method,'GET');return {can_edit:true,image:null}
    },async(path,selected,caption)=>{assert.equal(path,'planning/templates/2/image/');assert.equal(selected,file);assert.equal(caption,'Portada española');if(rejected)throw new Error('Formato inválido');return {image:{url:'/cover/',caption},can_edit:true,revision:'b'}})
    try{
        field(mounted.root,'Nombre de la plantilla').props['onUpdate:modelValue']('Semana')
        field(mounted.root,'Portada opcional de la nueva plantilla (hasta 5 MiB)').props['onUpdate:modelValue'](file)
        field(mounted.root,'Descripción de la portada').props['onUpdate:modelValue']('Portada española');await flush()
        await button(mounted.root,'Guardar nueva plantilla').props.onClick();await flush();assert.equal(posts,1);assert.match(textOf(mounted.root),/Plantilla guardada; no se ha podido/);assert.equal(field(mounted.root,'Portada opcional de la nueva plantilla (hasta 5 MiB)').props.modelValue,file)
        rejected=false;await button(mounted.root,'Reintentar portada').props.onClick();await flush();assert.equal(posts,1);assert.match(textOf(mounted.root),/Plantilla guardada/);assert.equal(field(mounted.root,'Portada opcional de la nueva plantilla (hasta 5 MiB)').props.modelValue,null)
    }finally{mounted.close()}
})
test('PNG and PDF revalidate the prepared snapshot and render downloadable documents',async()=>{
    let prints=0;globalThis.__cuadernoExportCalls=[]
    const mounted=await mountFunctional('./pages/MenuPlanningPage.vue',{},(path,method,body)=>{
        if(path==='edition/')return {edition:'profesional'}
        if(path.startsWith('planning/?'))return {...data,can_edit:false}
        if(path.startsWith('planning/templates/?'))return {count:1,results:[{id:2,name:'Semana',weeks:1,revision:'a',entries:[]}]}
        assert.equal(path,'planning/print/');assert.equal(method,'POST');assert.deepEqual(body.menus,[{name:'Menú',meal_plan_ids:[7],template_id:2}]);prints++
        return {orientation:'portrait',menus:[{name:'Menú',entries:[meal]}],declaration:'Manual',diet:null,diet_label:null,merged:false}
    })
    try{
        field(mounted.root,'Platos del periodo').props['onUpdate:modelValue']([7]);field(mounted.root,'Portada de una plantilla (opcional)').props['onUpdate:modelValue'](2);await flush()
        button(mounted.root,'Añadir menú a la impresión').props.onClick();await flush();await button(mounted.root,'Preparar documento').props.onClick();await flush()
        field(mounted.root,'Orientación').props['onUpdate:modelValue']('landscape');field(mounted.root,'Declaración dietética en el documento (opcional)').props['onUpdate:modelValue']('diabetes');await flush()
        await button(mounted.root,'Descargar PNG').props.onClick();await flush();await button(mounted.root,'Descargar PDF').props.onClick();await flush()
        assert.equal(prints,3);assert.deepEqual(globalThis.__cuadernoExportCalls.map(c=>c.format),['png','pdf']);assert.match(textOf(mounted.root),/PDF descargado: 2 páginas/);assert.match(textOf(mounted.root),/permiso para varias descargas/)
    }finally{mounted.close();delete globalThis.__cuadernoExportCalls}
})

test('creating a template with a cover refreshes the real image panel after its initial empty read', async () => {
    let savedImage = null, posts = 0, imageReads = 0
    const saved = {id: 2, name: 'Semana con portada', weeks: 1, revision: 'a', entries: []}
    const image = {url: '/api/cuaderno/planning/templates/2/image/content/?v=0123456789abcdef', caption: 'Portada recién guardada'}
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, async (path, method) => {
        if(path === 'edition/') return {edition: 'profesional'}
        if(path.startsWith('planning/?')) return data
        if(path === 'planning/templates/?offset=0&limit=50') return {count: posts, results: posts ? [{...saved, image: savedImage}] : []}
        if(path === 'planning/templates/' && method === 'POST') {posts++; return saved}
        assert.equal(path, 'planning/templates/2/image/'); assert.equal(method, 'GET'); imageReads++
        return {can_edit: true, image: savedImage, revision: savedImage ? 'b' : 'a'}
    }, async () => {await flush(); savedImage = image; return {can_edit: true, image, revision: 'b'}}, {actualImagePanel: true})
    try {
        field(mounted.root, 'Nombre de la plantilla').props['onUpdate:modelValue']('Semana con portada')
        field(mounted.root, 'Portada opcional de la nueva plantilla (hasta 5 MiB)').props['onUpdate:modelValue'](new File(['png'], 'cover.png', {type: 'image/png'}))
        await flush(); await button(mounted.root, 'Guardar nueva plantilla').props.onClick(); await flush()
        assert.equal(posts, 1); assert.ok(imageReads >= 2)
        assert.match(textOf(mounted.root), /Portada recién guardada/)
        assert.ok(button(mounted.root, 'Cambiar imagen'))
        assert.equal(button(mounted.root, 'Guardar imagen'), undefined)
    } finally {mounted.close()}
})

test('the meal menu bounds its overlay without losing long labels or multiple read-only selections', async () => {
    const recipeName = 'Sopa gástrica con verduras y una descripción completa para distinguir el plato del calendario'
    const meals = [{...meal, recipe: {id: 3, name: recipeName}}, {...meal, id: 8, title: 'Segundo plato'}]
    let prepared = false
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if(path === 'edition/') return {edition: 'integral'}
        if(path.startsWith('planning/?')) return {...data, can_edit: false, can_merge_print: true, meal_plans: meals}
        if(path.startsWith('planning/templates/?')) return {count: 0, results: []}
        assert.equal(path, 'planning/print/'); assert.equal(method, 'POST')
        assert.deepEqual(body.menus, [{name: 'Menú', meal_plan_ids: [7, 8]}]); prepared = true
        return {orientation: 'portrait', menus: [{name: 'Menú', entries: meals}], declaration: 'Manual', diet: null, diet_label: null, merged: false}
    })
    try {
        const selection = field(mounted.root, 'Platos del periodo')
        // Native WebKit changed the list width from 720px to 744px while
        // delivering row observers; this menu needs a stable scoped width.
        assert.deepEqual(selection.props['menu-props'], {minWidth: 0, contentClass: 'cuaderno-menu-recipe-options'})
        const {descriptor} = parse(readFileSync(new URL('./pages/MenuPlanningPage.vue', import.meta.url), 'utf8'))
        const style = descriptor.styles.find(item => item.scoped)
        const compiled = compileStyle({source: style.content, filename: 'MenuPlanningPage.vue', id: 'data-v-menu-test', scoped: true})
        assert.deepEqual(compiled.errors, [])
        const css = compiled.code.replace(/\s+/g, '')
        // Teleported menu content must retain the class without an ancestor or
        // scope attribute, and override Vuetify's changing inline max-width.
        const overlayRule = css.match(/\.cuaderno-menu-recipe-options\{([^}]+)\}/)?.[1]
        assert.ok(overlayRule)
        assert.ok(overlayRule.includes('width:min(38rem,calc(100vw-48px))!important;'))
        assert.ok(overlayRule.includes('max-width:min(38rem,calc(100vw-48px))!important;'))
        assert.ok(overlayRule.includes('min-width:0!important;'))
        assert.ok(Object.hasOwn(selection.props, 'multiple')); assert.ok(Object.hasOwn(selection.props, 'chips'))
        assert.ok(selection.props.items.some(item => item.id === 7 && item.label.includes(recipeName)))
        assert.equal(field(mounted.root, 'Portada de una plantilla (opcional)').props['menu-props'], undefined)
        assert.equal(field(mounted.root, 'Orientación').props['menu-props'], undefined)
        assert.equal(field(mounted.root, 'Declaración dietética en el documento (opcional)').props['menu-props'], undefined)
        selection.props['onUpdate:modelValue']([7, 8]); await flush()
        button(mounted.root, 'Añadir menú a la impresión').props.onClick(); await flush()
        await button(mounted.root, 'Preparar documento').props.onClick(); await flush()
        assert.equal(prepared, true); assert.match(textOf(mounted.root), /Sopa gástrica con verduras/)
    } finally {mounted.close()}
})
