/** Regenera únicamente configuración local de agentes. No llama a modelos ni a la red. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const routingPath = 'tooling/model-routing.json';
const routing = read(routingPath);
const roles = read('tooling/agent-roles.json').roles;
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--worker-model')) {
  throw new Error('Uso: node tools/configure-agents.mjs [--worker-model ID_VERIFICADO]');
}
if (args.length) {
  if (!/^gpt-[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(args[1])) {
    throw new Error('Identificador de modelo inválido. No uses etiquetas del selector como un ID.');
  }
  routing.worker.model = args[1];
  routing.interpretation = `Variante worker seleccionada explícitamente: ${args[1]} / ${routing.worker.reasoningEffort}. Disponibilidad pendiente de verificar.`;
}
function validModel(v) {
  if (!/^gpt-[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(v.model)) throw new Error('Modelo inválido');
  if (!['low','medium','high','xhigh','max','ultra'].includes(v.reasoningEffort)) throw new Error('Esfuerzo inválido');
}
for (const kind of ['leader', 'worker', 'reviewer']) validModel(routing[kind]);
const quote = JSON.stringify;
function write(rel, body) {
  const target = path.join(root, rel);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, body + '\n', 'utf8');
}
write(routingPath, JSON.stringify(routing, null, 2));
write('.codex/config.toml', [
  '# Configuración propuesta para el esquema documentado el 28/09/2026.',
  '# T001 debe verificar versión de cliente, confianza del repo y modelos efectivos.',
  `model = ${quote(routing.leader.model)}`,
  `model_reasoning_effort = ${quote(routing.leader.reasoningEffort)}`,
  'approval_policy = "on-request"',
  'sandbox_mode = "workspace-write"',
  '', '[agents]', 'enabled = true',
  `max_concurrent_threads_per_session = ${routing.maxConcurrentSubagents}`,
  `default_subagent_model = ${quote(routing.worker.model)}`,
  `default_subagent_reasoning_effort = ${quote(routing.worker.reasoningEffort)}`
].join('\n'));
for (const role of roles) {
  const model = routing[role.routing];
  write(`.codex/agents/${role.name}.toml`, [
    `name = ${quote(role.name)}`,
    `description = ${quote(role.description)}`,
    `model = ${quote(model.model)}`,
    `model_reasoning_effort = ${quote(model.reasoningEffort)}`,
    `sandbox_mode = ${quote(role.sandbox)}`,
    `developer_instructions = ${quote(role.instructions.join('\n'))}`
  ].join('\n'));
}
console.log(`Configuración local generada: líder ${routing.leader.model}; workers ${routing.worker.model}/${routing.worker.reasoningEffort}; ${roles.length} roles.`);
console.log('Esto no verifica disponibilidad de modelos ni ejecuta agentes. T001 debe comprobarlo.');
