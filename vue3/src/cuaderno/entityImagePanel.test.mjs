import test from 'node:test'
import assert from 'node:assert/strict'
import {mountFunctional, button, field, textOf, flush} from './functionalComponentHarness.mjs'
const image = {url:'/api/cuaderno/foods/9/image/content/',caption:'Tomate de prueba'}
test('Consulta sees food image but cannot upload, enter URLs or delete', async () => {
    const mounted = await mountFunctional('./components/EntityImagePanel.vue',{entityId:9,kind:'food'},(path,method)=>{assert.equal(path,'foods/9/image/');assert.equal(method,'GET');return {image,can_edit:false}})
    try {assert.match(textOf(mounted.root),/Tomate de prueba/);assert.match(textOf(mounted.root),/Modo Consulta/);assert.equal(field(mounted.root,'Foto del ingrediente (hasta 5 MiB)'),undefined);assert.equal(button(mounted.root,'Eliminar imagen'),undefined)} finally {mounted.close()}
})
test('failed image upload retains file and caption, retry saves only image', async () => {
    let rejected=true, uploads=0
    const file=new File([new Uint8Array(150)],'tomate.png',{type:'image/png'})
    const mounted=await mountFunctional('./components/EntityImagePanel.vue',{entityId:9,kind:'food'},(_path,method)=>{assert.equal(method,'GET');return {image:null,can_edit:true}},async(path,selected,caption)=>{uploads++;assert.equal(path,'foods/9/image/');assert.equal(selected,file);assert.equal(caption,'Tomate español');if(rejected) throw new Error('Archivo dañado');return {image,can_edit:true}})
    try {
        field(mounted.root,'Foto del ingrediente (hasta 5 MiB)').props['onUpdate:modelValue'](file)
        field(mounted.root,'Descripción de la imagen').props['onUpdate:modelValue']('Tomate español');await flush()
        await button(mounted.root,'Guardar imagen').props.onClick();await flush()
        assert.match(textOf(mounted.root),/Archivo dañado/);assert.equal(field(mounted.root,'Foto del ingrediente (hasta 5 MiB)').props.modelValue,file);assert.equal(field(mounted.root,'Descripción de la imagen').props.modelValue,'Tomate español')
        rejected=false;await button(mounted.root,'Guardar imagen').props.onClick();await flush()
        assert.equal(uploads,2);assert.equal(field(mounted.root,'Foto del ingrediente (hasta 5 MiB)').props.modelValue,null);assert.match(textOf(mounted.root),/Imagen guardada/);assert.equal(mounted.calls.filter(c=>c.method!=='GET').length,0)
    } finally {mounted.close()}
})
test('image deletion requires confirmation and rechecks a revoked permission', async () => {
    let permission=true
    const mounted=await mountFunctional('./components/EntityImagePanel.vue',{entityId:2,kind:'template'},(_path,method)=>{assert.equal(method,'GET');return {image,can_edit:permission}})
    try {
        button(mounted.root,'Eliminar imagen').props.onClick();await flush();assert.ok(button(mounted.root,'Confirmar eliminación'));assert.equal(mounted.calls.length,1)
        permission=false;await button(mounted.root,'Confirmar eliminación').props.onClick();await flush()
        assert.match(textOf(mounted.root),/acceso ha cambiado/);assert.equal(button(mounted.root,'Guardar imagen'),undefined);assert.equal(mounted.calls.length,2)
    } finally {mounted.close()}
})
