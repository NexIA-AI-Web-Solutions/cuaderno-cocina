/** Inventario local sin instalar nada y sin llamar APIs de modelos. Ejecutar con Node 24. */
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
function version(program){
 const win=process.platform==='win32';
 // Programas constantes, nunca entrada de usuario interpolada en shell.
 const r=win?spawnSync('cmd.exe',['/d','/s','/c',`${program} --version`],{encoding:'utf8',cwd:root,timeout:15000}):spawnSync(program,['--version'],{encoding:'utf8',cwd:root,timeout:15000});
 return {available:r.status===0,version:r.status===0?r.stdout.trim().slice(0,500):null};
}
const major=Number(process.versions.node.split('.')[0]);
const report={recordedAt:new Date().toISOString(),kind:'LOCAL_ENVIRONMENT_ONLY',os:process.platform,arch:process.arch,node:process.versions.node,node24:major===24,git:version('git'),pnpm:version('pnpm'),codex:version('codex'),modelRoutingVerified:false,sqliteEmbeddedVersion:'NOT_INSTALLED',applicationTests:'NOT_RUN'};
fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
fs.writeFileSync(path.join(root,'artifacts','preflight-local.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
console.log('Este inventario no verifica modelos ni sustituye T001. La app todavía debe construirse.');
if(!report.node24||!report.git.available)process.exitCode=1;
