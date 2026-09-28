import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const product=read('tooling/product.json');
const cases=read('examples/contracts/golden-cases.json').cases;
const fixture=read('examples/import/canonical-v1.json');
const c=id=>cases.find(v=>v.id===id);
// Oráculo racional independiente para comprobar ejemplos del plan, no código del producto.
function gcd(a,b){while(b){[a,b]=[b,a%b];}return a;}
function rat(n,d=1n){assert(d>0n); const g=gcd(n<0n?-n:n,d); return [n/g,d/g];}
function add([a,b],[c,d]){return rat(a*d+c*b,b*d);}
function mul([a,b],[c,d]){return rat(a*c,b*d);}
function round([n,d]){assert(n>=0n);return (2n*n+d)/(2n*d);}
function decimal(s){assert.match(s,/^\d+(\.\d+)?$/);const [i,f='']=s.split('.');return rat(BigInt(i+f),10n**BigInt(f.length));}

test('Última oferta y primer año, sin tarifas de borradores anteriores',()=>{
 assert.deepEqual(product.tiers.map(t=>[t.setupEur,t.monthlyEur,t.firstYearEur]),[[500,17,704],[1000,20,1240],[1500,30,1860]]);
});
test('Capacidades acumulativas sin ciclos',()=>{
 const seen=new Set();for(const t of product.tiers){if(t.inherits)assert(seen.has(t.inherits));seen.add(t.id);}
 assert.equal(product.defaultEdition,'esencial');
});
for(const id of ['C01','C02'])test(`${id}: precio por formato y ración exactos`,()=>{
 const v=c(id);const total=rat(BigInt(v.packageCents*v.usedMl),BigInt(v.packageMl));
 assert.equal(round(total),BigInt(v.expectedTotalCents));
 assert.equal(round(mul(total,rat(1n,BigInt(v.servings)))),BigInt(v.expectedServingCents));
});
test('C03: escalado sin pérdida aritmética',()=>{const v=c('C03');assert.equal(round(rat(BigInt(v.baseMl*v.targetServings),BigInt(v.baseServings))),BigInt(v.expectedMl));});
test('C04/C05: desconocido distinto de gratis',()=>{assert.equal(c('C04').priceCents,null);assert.equal(c('C05').priceCents,0);assert.notEqual(c('C04').expectedStatus,c('C05').expectedStatus);});
test('C06: rendimiento 80% aplicado una vez',()=>{const v=c('C06'),[n,d]=decimal(v.yield);assert.equal(round(rat(BigInt(v.packageCents)*d,n)),BigInt(v.expectedCostCents));});
test('C07: coste proporcional de subelaboración',()=>{const v=c('C07');assert.equal(round(rat(BigInt(v.batchCents*v.usedG),BigInt(v.batchG))),BigInt(v.expectedCostCents));});
test('C08: valoración operativa ponderada',()=>{
 const v=c('C08');const kg=v.receipts.reduce((s,r)=>s+r.kg,0);const cents=v.receipts.reduce((s,r)=>s+r.kg*r.centsPerKg,0);
 assert.equal(kg-v.consumeKg-v.wasteKg,v.expectedRemainingKg);
 assert.equal(round(rat(BigInt(cents*v.expectedRemainingKg),BigInt(kg))),BigInt(v.expectedRemainingCents));
 assert.equal(round(rat(BigInt(cents*v.wasteKg),BigInt(kg))),BigInt(v.expectedWasteCents));
});
test('C09: sumar antes de redondear',()=>{const v=c('C09');assert.equal(round(rat(BigInt(v.lines*v.numeratorCents),BigInt(v.denominator))),BigInt(v.expectedRoundedTotalCents));});
test('Fixture canónica: referencias únicas, cantidades y coste 4,08 €',()=>{
 const byId=new Map(fixture.ingredients.map(i=>[i.externalId,i]));assert.equal(byId.size,fixture.ingredients.length);
 let total=rat(0n);const recipe=fixture.recipes[0];
 for(const line of recipe.lines){const i=byId.get(line.ingredientExternalId);assert(i);const p=i.purchaseFormat;assert.equal(p.unit,line.unit);const [qn,qd]=decimal(line.quantity);const [pn,pd]=decimal(p.quantity);total=add(total,rat(BigInt(p.priceCents)*qn*pd,qd*pn));}
 assert.equal(round(total),BigInt(fixture.expectedForFixtureOnly.recipeTotalCents));
 assert.equal(round(mul(total,rat(1n,BigInt(recipe.servings)))),BigInt(fixture.expectedForFixtureOnly.perServingCents));
});
test('Plan sin tareas huérfanas o dependencias futuras',()=>{
 const tasks=read('tooling/work-packets.json').tasks,seen=new Set();
 for(const t of tasks){for(const d of t.dependsOn)assert(seen.has(d));assert(!seen.has(t.id));seen.add(t.id);}
 assert.equal(seen.size,34);
});
test('Routing explícito, revisión independiente y límites de escritores',()=>{
 const m=read('tooling/model-routing.json');assert.equal(m.leader.model,'gpt-5.6-sol');assert.equal(m.worker.reasoningEffort,'medium');assert.equal(m.maxConcurrentWriters,2);assert.equal(m.silentFallbackAllowed,false);
 const roles=read('tooling/agent-roles.json').roles;assert.equal(roles.find(r=>r.name==='cuaderno_reviewer').sandbox,'read-only');
});
test('Seguridad y datos sintéticos forman parte del contrato',()=>{
 assert.equal(fixture.dataOrigin,'SYNTHETIC');
 assert.equal(c('C10').expectedError,'RECIPE_CYCLE');assert.equal(c('C11').expectedError,'UNIT_DIMENSION_MISMATCH');
 assert.equal(c('C12').expectedPostedReceipts,1);assert.equal(c('C14').expectedHttpStatus,403);
});
