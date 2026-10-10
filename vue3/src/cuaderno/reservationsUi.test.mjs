import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source = readFileSync(new URL('./reservationsUi.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { reservationBody, reservationActions, reservationStateLabel, menuKey, summaryGroupKey, reservationHistoryText, reservationHistoryAction } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const menu = { template: 3, template_day: 0, meal_type: 2 };
const draft = { customer_name: ' Ana ', phone: ' 600123456 ', email: '', service_date: '2026-10-10', service_time: '13:30', covers: '20', note: '', reason: ' llamada ', menu };
test('contact, integer covers and reason validated without erasing draft', () => { const result = reservationBody(draft); assert.equal(result.errors.length, 0); assert.equal(result.body.customer_name, 'Ana'); assert.equal(result.body.covers, 20); assert.equal(result.body.reason, 'llamada'); assert.equal(draft.customer_name, ' Ana '); for (const covers of ['0', '10000', '1.5', '1e2', 'NaN'])
    assert.ok(reservationBody({ ...draft, covers }).errors.length); assert.ok(reservationBody({ ...draft, phone: '', email: '' }).errors.length); assert.ok(reservationBody({ ...draft, reason: '' }).errors.length); });
test('rejects invalid dates, times and invalid email while allowing email-only contact', () => { assert.ok(reservationBody({ ...draft, service_date: '2026-02-30' }).errors.length); assert.ok(reservationBody({ ...draft, service_time: '25:00' }).errors.length); assert.ok(reservationBody({ ...draft, email: 'invalid' }).errors.length); assert.equal(reservationBody({ ...draft, phone: '', email: 'ana@example.test' }).errors.length, 0); });
test('Consulta no transitions; Cocina confirms/starts/serves; only Responsable cancels', () => { for (const state of ['requested', 'confirmed', 'in_kitchen', 'served', 'cancelled'])
    assert.deepEqual(reservationActions(state, false, false), []); assert.deepEqual(reservationActions('requested', true, false), ['confirm']); assert.deepEqual(reservationActions('confirmed', true, false), ['start_kitchen']); assert.deepEqual(reservationActions('in_kitchen', true, false), ['serve']); assert.deepEqual(reservationActions('confirmed', true, true), ['start_kitchen', 'cancel']); assert.deepEqual(reservationActions('served', true, true), []); assert.deepEqual(reservationActions('unknown', true, true), []); });
test('menu identities include template day and meal type; labels are Spanish', () => { assert.notEqual(menuKey(menu), menuKey({ ...menu, template_day: 1 })); assert.notEqual(menuKey(menu), menuKey({ ...menu, meal_type: 3 })); assert.equal(reservationStateLabel('in_kitchen'), 'En cocina'); assert.equal(reservationStateLabel('unknown'), 'Estado desconocido'); });
test('maximum lengths match backend customer160 phone64 note1000 and preserve limits', () => { for (const [field, length] of [['customer_name', 160], ['phone', 64], ['note', 1000]]) {
    assert.equal(reservationBody({ ...draft, [field]: 'a'.repeat(length) }).errors.length, 0);
    assert.ok(reservationBody({ ...draft, [field]: 'a'.repeat(length + 1) }).errors.length);
} assert.equal(reservationStateLabel('cancelled'), 'Anulada'); });

test('summary keys distinguish frozen menu versions without changing selection identity', () => {
    assert.equal(menuKey({...menu,menu_fingerprint:'old'}),menuKey({...menu,menu_fingerprint:'new'}));
    assert.notEqual(summaryGroupKey({...menu,menu_fingerprint:'old'}),summaryGroupKey({...menu,menu_fingerprint:'new'}));
});

test('history translates actions and before/after snapshots without raw identifiers or fingerprint', () => {
    const history = reservationHistoryText({id: 999, customer_name: 'Ana', phone: '600123456', service_date: '2026-10-12', service_time: '13:30', covers: 20, state: 'confirmed', template: 888, template_day: 0, menu_snapshot: {fingerprint: 'secret-version', dishes: [{recipe_id: 777, recipe_name: 'Arroz', course_name: 'Primero'}]}});
    assert.match(history, /Cliente: Ana/); assert.match(history, /Fecha: 12\/10\/2026/); assert.match(history, /Comensales: 20/); assert.match(history, /Estado: Confirmada/); assert.match(history, /Plato: Primero: Arroz/);
    assert.doesNotMatch(history, /999|888|777|fingerprint|secret-version|confirmed|customer_name/);
    assert.equal(reservationHistoryAction('edit'), 'Datos editados'); assert.equal(reservationHistoryAction('start_kitchen'), 'Paso a cocina');
});
test('time is minute-only as server contract, no seconds accepted', () => {
    for (const service_time of ['13:30:01', '13:30:00']) assert.ok(reservationBody({...draft, service_time}).errors.length);
});
