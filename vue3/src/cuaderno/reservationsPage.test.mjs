// Real SFC logic and render, with transport/widgets as unit boundaries. Browser acceptance is separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, compileScript } from '@vue/compiler-sfc';
import ts from 'typescript';
import * as Vue from 'vue';
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
const helper = name => moduleUrl(ts.transpileModule(readFileSync(new URL(name, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText);
const all = (root, p) => { const result = []; const visit = n => { if (p(n))
    result.push(n); for (const child of n.children || [])
    visit(child); }; visit(root); return result; };
const textOf = root => all(root, n => n.type === '#text').map(n => n.text).join(' ');
const button = (root, label) => all(root, n => n.type === 'button' && textOf(n).trim() === label)[0];
const input = (root, label) => all(root, n => n.type === 'input' && n.props.label === label)[0];
async function flush() { for (let i = 0; i < 12; i++) {
    await Vue.nextTick();
    await new Promise(r => setImmediate(r));
} }
function renderer() { return Vue.createRenderer({ createElement: type => ({ type, props: {}, children: [], parent: null }), createText: text => ({ type: '#text', text, children: [], parent: null }), createComment: text => ({ type: '#comment', text, children: [], parent: null }), setText: (n, t) => { n.text = t; }, setElementText: (n, t) => { n.children = [{ type: '#text', text: t, children: [], parent: n }]; }, parentNode: n => n.parent, nextSibling: n => n.parent?.children[n.parent.children.indexOf(n) + 1] || null, insert(n, p, a = null) { if (n.parent) {
        const i = n.parent.children.indexOf(n);
        if (i >= 0)
            n.parent.children.splice(i, 1);
    } n.parent = p; const i = a ? p.children.indexOf(a) : -1; i < 0 ? p.children.push(n) : p.children.splice(i, 0, n); }, remove(n) { if (n.parent) {
        const i = n.parent.children.indexOf(n);
        if (i >= 0)
            n.parent.children.splice(i, 1);
        n.parent = null;
    } }, patchProp: (n, k, o, v) => { n.props[k] = v; }, setScopeId() { }, insertStaticContent() { assert.fail('Static hoist disabled'); } }); }
const menu = { template: 3, template_name: 'Menú <seguro>', template_day: 0, meal_type: 2, meal_type_name: 'Comida', dishes: [{ recipe_id: 7, recipe_name: 'Arroz' }] };
const row = { id: 1, customer_name: 'Ana', phone: '600123456', email: '', service_date: '2026-10-10', service_time: '13:30:00', ...menu, covers: 20, note: '', state: 'confirmed', revision: 9, can_operate: true, can_edit: true, can_change_menu: true, can_cancel: true, menu_snapshot: { dishes: menu.dishes }, services: [{ id: 5, state: 'confirmed' }], history: [{ revision: 9, action: 'update', reason: 'Cambio teléfono', before: { phone: '600000000' }, after: { phone: '600123456' }, created_at: '2026-10-10T10:00:00Z' }] };
const summary = { date: '2026-10-10', pending_covers: 75, total_active_covers: 75, in_kitchen_covers: 0, groups: [{ ...menu, menu_fingerprint: 'version-a', pending_covers: 75, confirmed_covers: 75, total_active_covers: 75, in_kitchen_covers: 0, reservations: [1, 2, 3, 4], dishes: [{ recipe_id: 7, recipe_name: 'Arroz', pending_servings: 75, in_kitchen_servings: 0, total_active_servings: 75 }], needs: [{ food_id: 2, food_name: 'Arroz', unit_id: 3, unit_name: 'kg', quantity: '7.5000000000000001' }], warnings: [], service_ids: [5] }] };
let sequence = 0;
async function mount(role = 'user', custom) {
    const id = ++sequence, calls = [];
    globalThis.__reservationTransport ??= new Map();
    globalThis.__reservationTransport.set(id, async (url, options = {}) => { calls.push({ url, options }); if (custom) {
        const result = custom(url, options);
        if (result)
            return result;
    } let data; if (url.includes('/edition/'))
        data = { edition: 'profesional', operational_role: { code: role, label: { guest: 'Consulta', user: 'Cocina', admin: 'Responsable' }[role], space: 12, can_operate_cuaderno: role !== 'guest', can_manage_edition: role === 'admin', native_permissions_preserved: true } };
    else if (url.includes('/summary/'))
        data = summary;
    else if (url.includes('/menus/'))
        data = { results: [menu] };
    else if (/reservations\/1\/$/.test(url))
        data = row;
    else
        data = { count: 1, offset: 0, limit: 50, results: [row], can_operate: role !== 'guest', can_manage: role === 'admin' }; return { ok: true, status: 200, data }; });
    const api = moduleUrl(`export const cuadernoFetch=(url,options)=>globalThis.__reservationTransport.get(${id})(url,options);export const readJson=async response=>response;`);
    const { descriptor, errors } = parse(readFileSync(new URL('./pages/ReservasPage.vue', import.meta.url), 'utf8'));
    assert.deepEqual(errors, []);
    let code = ts.transpileModule(compileScript(descriptor, { id: 'reservas-' + id, inlineTemplate: true, templateOptions: { compilerOptions: { hoistStatic: false } } }).content, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
    const deps = new Map([['vue', import.meta.resolve('vue')], ['@/cuaderno/api', api], ['@/cuaderno/operationalRoleUi', helper('./operationalRoleUi.ts')], ['@/cuaderno/reservationsUi', helper('./reservationsUi.ts')]]);
    code = code.replace(/from (["'])([^"']+)\1/g, (o, q, name) => { assert.ok(deps.has(name), name); return `from ${JSON.stringify(deps.get(name))}`; });
    const component = (await import(moduleUrl(code))).default, root = { type: 'root', props: {}, children: [], parent: null }, app = renderer().createApp(component);
    for (const name of ['v-container', 'v-alert', 'v-progress-linear', 'v-btn', 'v-row', 'v-col', 'v-card', 'v-card-title', 'v-card-text', 'v-card-actions', 'v-chip', 'v-text-field', 'v-textarea', 'v-select', 'v-dialog'])
        app.component(name, Vue.defineComponent({ inheritAttrs: false, props: name === 'v-dialog' ? { modelValue: { default: undefined } } : {}, setup(p, c) { return () => { if (name === 'v-dialog' && !p.modelValue)
                return null; const type = name === 'v-btn' ? 'button' : ['v-text-field', 'v-textarea', 'v-select'].includes(name) ? 'input' : name; return Vue.h(type, { ...c.attrs }, c.slots.default?.()); }; } }));
    app.mount(root);
    await flush();
    return { root, calls, close() { app.unmount(); globalThis.__reservationTransport.delete(id); } };
}
async function click(root, label) { const b = button(root, label); assert.ok(b, `button ${label}`); assert.ok(!b.props.disabled, `enabled ${label}`); await b.props.onClick(); await flush(); }
function change(root, label, value) { const i = input(root, label); assert.ok(i, label); i.props['onUpdate:modelValue'](value); }
test('Consulta reads exact consolidated needs, actual75 servings, details/history and no mutation controls', async () => { const m = await mount('guest'); assert.match(textOf(m.root), /pendientes del día: 75/); assert.match(textOf(m.root), /7\.5000000000000001 kg/); assert.match(textOf(m.root), /pendientes 75, en cocina 0, total 75/); for (const label of ['Nueva reserva', 'Editar', 'Pasar a cocina', 'Anular reserva'])
    assert.equal(button(m.root, label), undefined); await click(m.root, 'Ver detalles e historial'); assert.match(textOf(m.root), /600000000/); assert.match(textOf(m.root), /600123456/); assert.equal(all(m.root, n => n.type === 'script').length, 0); m.close(); });
test('Cocina edit sends current revision/reason and only changed basic fields, omits menu', async () => { const m = await mount('user'); await click(m.root, 'Editar'); assert.equal(input(m.root, 'Menú guardado, día y servicio').props.disabled, true); change(m.root, 'Número de comensales', '30'); change(m.root, 'Motivo del registro o cambio', 'Llamada cliente'); await click(m.root, 'Guardar cambios'); const call = m.calls.find(c => c.options.method === 'PATCH'); assert.deepEqual(JSON.parse(call.options.body), { covers: 30, reason: 'Llamada cliente', revision: 9 }); m.close(); });
test('409 preserves draft and blocks stale retry; explicit reload replaces with current revision', async () => { const m = await mount('admin', (url, o) => o.method === 'PATCH' ? { ok: false, status: 409, data: { detail: 'Revisión obsoleta' } } : url.endsWith('/reservations/1/') ? { ok: true, status: 200, data: { ...row, revision: 10, covers: 35 } } : null); await click(m.root, 'Editar'); change(m.root, 'Número de comensales', '30'); change(m.root, 'Motivo del registro o cambio', 'Llamada'); await click(m.root, 'Guardar cambios'); assert.equal(input(m.root, 'Número de comensales').props.modelValue, '30'); assert.equal(button(m.root, 'Guardar cambios').props.disabled, true); assert.match(textOf(m.root), /borrador se conserva/); await click(m.root, 'Recargar y sustituir borrador'); assert.equal(input(m.root, 'Número de comensales').props.modelValue, '35'); assert.match(textOf(m.root), /editando: 10/); assert.equal(button(m.root, 'Guardar cambios').props.disabled, false); m.close(); });
test('kitchen transition requires reason and visible stock confirmation before sending action', async () => { const m = await mount('user'); assert.equal(button(m.root, 'Anular reserva'), undefined); await click(m.root, 'Pasar a cocina'); assert.match(textOf(m.root), /Integral se consumirán ingredientes/); await click(m.root, 'Confirmar acción'); assert.equal(m.calls.filter(c => c.options.method === 'POST').length, 0); change(m.root, 'Motivo de la acción', 'Inicio preparación'); await click(m.root, 'Confirmar acción'); const call = m.calls.find(c => c.options.method === 'POST'); assert.deepEqual(JSON.parse(call.options.body), { action: 'start_kitchen', revision: 9, reason: 'Inicio preparación' }); m.close(); });
test('creation validates contact and covers; valid create sends complete menu identity', async () => { const m = await mount('user'); await click(m.root, 'Nueva reserva'); await click(m.root, 'Registrar reserva'); assert.equal(m.calls.filter(c => c.options.method === 'POST').length, 0); change(m.root, 'Cliente', 'Bea'); change(m.root, 'Teléfono', '611123456'); change(m.root, 'Fecha del servicio', '2026-10-10'); change(m.root, 'Hora del servicio', '14:00'); change(m.root, 'Menú guardado, día y servicio', '3:0:2'); change(m.root, 'Número de comensales', '15'); change(m.root, 'Motivo del registro o cambio', 'Llamada nueva'); await click(m.root, 'Registrar reserva'); const call = m.calls.find(c => c.options.method === 'POST'); assert.deepEqual(JSON.parse(call.options.body), { customer_name: 'Bea', phone: '611123456', email: '', service_date: '2026-10-10', service_time: '14:00', covers: 15, note: '', reason: 'Llamada nueva', template: 3, template_day: 0, meal_type: 2 }); m.close(); });
test('served or in-kitchen rows cannot open editor even if stale server can_edit is true', async () => { for (const state of ['served', 'in_kitchen']) {
    const m = await mount('admin', (url) => url.includes('/reservations/?') ? { ok: true, status: 200, data: { count: 1, results: [{ ...row, state, can_edit: true }] } } : null);
    assert.equal(button(m.root, 'Editar'), undefined);
    if (state === 'served')
        for (const action of ['Confirmar reserva', 'Pasar a cocina', 'Marcar servida', 'Anular reserva'])
            assert.equal(button(m.root, action), undefined);
    m.close();
} });
test('Esencial feature unavailable and malformed operational role fail closed', async () => { const esencial = await mount('admin', (url) => url.includes('/edition/') ? { ok: true, status: 200, data: { edition: 'esencial' } } : null); assert.match(textOf(esencial.root), /disponibles en Profesional e Integral/); assert.equal(esencial.calls.some(c => c.url.includes('/reservations/')), false); esencial.close(); const malformed = await mount('admin', (url) => url.includes('/edition/') ? { ok: true, status: 200, data: { edition: 'integral', operational_role: { code: 'admin', can_operate_cuaderno: true } } } : null); assert.equal(button(malformed.root, 'Nueva reserva'), undefined); assert.equal(button(malformed.root, 'Editar'), undefined); malformed.close(); });
test('Cocina reading another household sees details but no edits or transitions; own admin access unchanged',async()=>{
    const transport=(url)=>url.includes('/reservations/?')?{ok:true,status:200,data:{count:1,results:[{...row,can_operate:false,can_edit:false,can_change_menu:false,can_cancel:false}]}}:null;
    const cook=await mount('user',transport);
    assert.ok(button(cook.root,'Ver detalles e historial'));
    for(const label of ['Editar','Confirmar reserva','Pasar a cocina','Marcar servida','Anular reserva'])assert.equal(button(cook.root,label),undefined,label);
    cook.close();
    const admin=await mount('admin');assert.ok(button(admin.root,'Editar'));assert.ok(button(admin.root,'Pasar a cocina'));assert.ok(button(admin.root,'Anular reserva'));admin.close();
});
test('missing per-row permission fails closed even for globally operational Cocina',async()=>{
    const cook=await mount('user',(url)=>{if(!url.includes('/reservations/?'))return null;const {can_operate,...legacy}=row;return {ok:true,status:200,data:{count:1,results:[legacy]}}});
    assert.equal(button(cook.root,'Pasar a cocina'),undefined);cook.close();
});
test('two frozen versions of one menu remain separately visible when summary order changes',async()=>{
    let reversed=false;const first={...summary.groups[0],menu_fingerprint:'old',needs:[{food_id:2,food_name:'Arroz anterior',quantity:'1',unit_name:'kg'}]},second={...summary.groups[0],menu_fingerprint:'new',needs:[{food_id:2,food_name:'Arroz actualizado',quantity:'2',unit_name:'kg'}]};
    const m=await mount('guest',(url)=>url.includes('/summary/')?{ok:true,status:200,data:{...summary,groups:reversed?[second,first]:[first,second]}}:null);
    assert.match(textOf(m.root),/Arroz anterior: 1 kg/);assert.match(textOf(m.root),/Arroz actualizado: 2 kg/);
    reversed=true;await click(m.root,'Actualizar día');const text=textOf(m.root);assert.ok(text.indexOf('Arroz actualizado')<text.indexOf('Arroz anterior'));m.close();
});
test('no assigned household disables creation for both Cocina and Responsable with useful explanation',async()=>{
    for(const role of ['user','admin']){const m=await mount(role,(url)=>url.includes('/reservations/?')?{ok:true,status:200,data:{count:0,results:[],can_operate:false,can_manage:role==='admin'}}:null);assert.equal(button(m.root,'Nueva reserva'),undefined);assert.match(textOf(m.root),/Necesitas un hogar operativo asignado/);assert.equal(m.calls.some(call=>call.options.method==='POST'),false);m.close()}
});
