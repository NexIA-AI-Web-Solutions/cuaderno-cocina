/** Comprobación de integridad lógica del paquete, NO de la aplicación. */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const product = read('tooling/product.json');
const routing = read('tooling/model-routing.json');
const tasks = read('tooling/work-packets.json').tasks;
const roles = read('tooling/agent-roles.json').roles;
for (const p of ['AGENTS.md','README.md','START_HERE_ES.md','CODEX_START_PROMPT.md','CODEX_RESUME_PROMPT.md','docs/00-SCOPE.md','docs/12-DEFINITION-OF-DONE.md','.codex/config.toml']) {
  assert(fs.existsSync(path.join(root,p)), `Falta ${p}`);
}
assert.equal(product.defaultEdition,'esencial');
assert.equal(product.engineeringTarget,'ALL_TIERS');
assert.deepEqual(product.tiers.map(t => [t.setupEur,t.monthlyEur]),[[500,17],[1000,20],[1500,30]]);
for (const t of product.tiers) assert.equal(t.firstYearEur, t.setupEur + 12*t.monthlyEur);
assert.equal(new Set(tasks.map(t => t.id)).size, 34);
const seen = new Set();
for (const t of tasks) {
  for (const d of t.dependsOn) assert(seen.has(d), `${t.id}: dependencia no anterior ${d}`);
  assert(t.acceptance && t.requiresIndependentReview, `Contrato incompleto ${t.id}`);
  seen.add(t.id);
}
assert.equal(tasks.at(-1).id,'T034');
assert.equal(routing.silentFallbackAllowed,false);
assert.equal(routing.worker.reasoningEffort,'medium');
for (const role of roles) {
  const body = fs.readFileSync(path.join(root,`.codex/agents/${role.name}.toml`),'utf8');
  assert(body.includes(`name = "${role.name}"`));
  assert(body.includes(`model = "${routing[role.routing].model}"`));
  assert(body.includes('developer_instructions = '));
}
assert.equal(roles.find(r=>r.name==='cuaderno_reviewer').sandbox,'read-only');
const skillDirs = fs.readdirSync(path.join(root,'.agents/skills'));
assert.equal(skillDirs.length,8);
for (const name of skillDirs) {
  const s = fs.readFileSync(path.join(root,'.agents/skills',name,'SKILL.md'),'utf8');
  assert(s.startsWith('---\n') && s.includes(`name: ${name}\n`) && s.includes('description: '));
}
const fixture = read('examples/import/canonical-v1.json');
assert.equal(fixture.dataOrigin,'SYNTHETIC');
console.log('HANDOFF_OK: 3 ediciones, importes coherentes, 34 tareas ordenadas, 5 roles y 8 skills.');
console.log('La aplicación no se ha validado con este comando. Solo comprueba el material de arranque.');
