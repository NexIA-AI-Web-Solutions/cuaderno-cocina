import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse,compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'
const data=code=>`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
let sequence=0
async function mount(file,expose,state,props={}){
 const key=++sequence;globalThis.__nativeUx??=new Map();globalThis.__nativeUx.set(key,state)
 let source=readFileSync(new URL('../components/'+file,import.meta.url),'utf8')
 source=source.replace(/\bPropType\s*,/g,'').replace(/,\s*PropType\b/g,'')
 const exposed=expose.map(name=>`${name}: typeof ${name} === 'undefined' ? null : ${name}`).join(',')
 const {descriptor}=parse(source.replace('</script>',`\ndefineExpose({${exposed}})\n</script>`))
 descriptor.template=null
 let code=compileScript(descriptor,{id:'native'+key}).content
 code=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
 code=code.replace(/import ([\s\S]*?) from (["'])([^"']+)\2;/g,(original,bindings,_q,path)=>{
  if(path==='vue')return original.replace(/from ["']vue["']/,'from '+JSON.stringify(import.meta.resolve('vue')))
  const special={
   ApiApi:`class { constructor(){return globalThis.__nativeUx.get(${key}).api} }`,
   useShoppingStore:`()=>globalThis.__nativeUx.get(${key}).shopping`,
   useUserPreferenceStore:`()=>globalThis.__nativeUx.get(${key}).preferences`,
   useMessageStore:`()=>globalThis.__nativeUx.get(${key}).messages`,
   ErrorMessageType:`{CREATE_ERROR:'create',FETCH_ERROR:'fetch'}`, PreparedMessage:`{CREATE_SUCCESS:'success'}`,
   INTEGRATIONS:`[]`,useI18n:`()=>({t:key=>key})`,useClipboard:`()=>({copy:()=>{}})`,
   isEntryVisible:`()=>true`,isShoppingCategoryVisible:`()=>true`,isShoppingListFoodVisible:`()=>true`,
   useDjangoUrls:`()=>({getDjangoUrl:path=>'/'+path})`,
  }
  let names=[];const named=bindings.match(/\{([\s\S]*?)\}/);if(named)names=named[1].split(',').map(x=>x.trim()).filter(Boolean)
  let exports=names.map(name=>{const [orig,alias]=name.split(/\s+as\s+/);return `export const ${orig}=${special[orig]||'()=>null'};`}).join('\n')
  exports+='\nexport default {render:()=>null};'
  return `import ${bindings} from ${JSON.stringify(data(exports))};`
 })
 const component=(await import(data(code))).default;component.render=()=>null
 const renderer=Vue.createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
 const app=renderer.createApp(component,props);const instance=app.mount({});await flush()
 return {instance,close(){app.unmount();globalThis.__nativeUx.delete(key)}}
}
async function flush(){for(let i=0;i<12;i++)await Vue.nextTick()}
const state=()=>({api:{},messages:{errors:[],addError(type,error){this.errors.push(type)},addPreparedMessage(){}},shopping:{shoppingLists:[],entriesByGroup:[]},preferences:{deviceSettings:{shopping_selected_shopping_lists:[]},userSettings:{csvDelim:';',csvPrefix:'-'}}})

test('native quick add keeps fractions, pending duplicate guard and success/failure drafts',async()=>{
 const s=state();let resolveParser,resolveCreate;let parses=0,creates=0,payload
 s.api.apiIngredientParserPostCreate=()=>{parses++;return new Promise(r=>resolveParser=r)}
 s.shopping.createObject=object=>{creates++;payload=object;return new Promise(r=>resolveCreate=r)}
 const m=await mount('inputs/ShoppingListEntryInput.vue',['parseIngredient','ingredientInput','loading','ingredientInputIcon'],s)
 try{
  m.instance.ingredientInput='  ';await m.instance.parseIngredient();assert.equal(parses,0,'blank never reaches parser')
  m.instance.ingredientInput='0,25 kg arroz';const first=m.instance.parseIngredient();m.instance.parseIngredient();assert.equal(parses,1)
  resolveParser({ingredient:{amount:'0.25',unit:{id:1},food:{id:2,name:'Arroz'}}});await flush()
  assert.equal(payload.amount,0.25);assert.equal(creates,1);assert.equal(m.instance.ingredientInput,'0,25 kg arroz');assert.notEqual(m.instance.ingredientInputIcon,'fa-solid fa-check')
  resolveCreate(undefined);await first;assert.equal(m.instance.ingredientInput,'0,25 kg arroz');assert.equal(m.instance.loading,false)
  const second=m.instance.parseIngredient();resolveParser({ingredient:{amount:'0.25',food:{id:2,name:'Arroz'}}});await flush();resolveCreate({id:3});await second
  assert.equal(m.instance.ingredientInput,'');assert.equal(m.instance.ingredientInputIcon,'fa-solid fa-check')
 }finally{m.close()}
})

test('related-recipe failure is recoverable and initial list-recipe create failure releases busy',async()=>{
 const s=state();let failRelated=true,creates=0
 s.api.apiRecipeRetrieve=()=>Promise.resolve({id:1,name:'Arroz',servings:2,steps:[]})
 s.api.apiRecipeRelatedList=()=>failRelated?Promise.reject(Error('offline')):Promise.resolve([])
 s.api.apiShoppingListRecipeCreate=()=>{creates++;return Promise.reject(Error('save failed'))}
 const m=await mount('dialogs/AddToShoppingDialog.vue',['loadRecipeData','createShoppingListRecipe','servings','loading','loadError','dialogRecipes'],s,{recipe:{id:1}})
 try{
  await flush();assert.equal(m.instance.loading,false);assert.ok(m.instance.loadError)
  failRelated=false;await m.instance.loadRecipeData();assert.equal(m.instance.loadError,'');assert.equal(m.instance.dialogRecipes.length,1)
  for(const invalid of [0,-1,NaN,Infinity]){m.instance.servings=invalid;await m.instance.createShoppingListRecipe()};assert.equal(creates,0)
  m.instance.servings=2;await m.instance.createShoppingListRecipe();assert.equal(creates,1);assert.equal(m.instance.loading,false)
 }finally{m.close()}
})

test('CSV escapes delimiter, quotes and newlines in headers, categories and entry fields',async()=>{
 const s=state();const m=await mount('dialogs/ShoppingExportDialog.vue',['mode','formatEntry','formatCategory'],s)
 try{m.instance.mode='csv';assert.equal(m.instance.formatEntry({amount:'0.25',unit:{name:'cuchara; grande'},food:{name:'Arroz "A"\nnuevo'}}),'0.25;"cuchara; grande";"Arroz ""A""\nnuevo"');assert.equal(m.instance.formatCategory('Secos; "A"'),'"Secos; ""A""";;')}finally{m.close()}
})

test('export poll failure releases loading and retry continues existing export, unmount stops timer',async()=>{
 const s=state();let fail=true,reads=0
 s.api.apiExportLogRetrieve=()=>{reads++;return fail?Promise.reject(Error('offline')):Promise.resolve({id:4,running:true})}
 const m=await mount('settings/ExportDataSettings.vue',['recRefreshExportLog','exportLog','loading','pollError'],s)
 try{m.instance.exportLog={id:4,running:true};m.instance.loading=true;await m.instance.recRefreshExportLog();assert.equal(m.instance.loading,false);assert.ok(m.instance.pollError);fail=false;await m.instance.recRefreshExportLog();assert.equal(m.instance.pollError,'');assert.equal(reads,2)}finally{m.close()}
 await new Promise(r=>setTimeout(r,1100));assert.equal(reads,2,'unmount cancels scheduled polling')
})

test('recipe card totals include waiting-only and ignore missing or nonfinite time values',async()=>{
 for(const [recipe,expected]of [[{waitingTime:20},20],[{workingTime:10},10],[{workingTime:10,waitingTime:20},30],[{workingTime:NaN,waitingTime:Infinity},0]]){
  const m=await mount('display/RecipeCard.vue',['totalMinutes'],state(),{recipe:{id:1,...recipe}})
  try{assert.equal(m.instance.totalMinutes,expected)}finally{m.close()}
 }
})

test('shopping download preserves hash and newline bytes using Blob and revokes the object URL',async()=>{
 const s=state();s.shopping.entriesByGroup=[{name:'Secos',foods:[{entries:[{amount:1,food:{name:'Arroz #1\nfin'}}]}]}]
 const m=await mount('dialogs/ShoppingExportDialog.vue',['downloadExport','mode','exportText'],s)
 const originalDocument=globalThis.document,originalRevoke=URL.revokeObjectURL;let clicked,removed=false,revoked
 const link={set href(value){this._href=value},get href(){return this._href},click(){clicked=this._href},remove(){removed=true}}
 globalThis.document={createElement:()=>link,body:{appendChild(){}}};URL.revokeObjectURL=url=>{revoked=url;originalRevoke(url)}
 try{
  m.instance.mode='csv';m.instance.downloadExport();assert.ok(clicked.startsWith('blob:'));assert.equal(removed,true)
  const downloaded=await(await fetch(clicked)).text();assert.equal(downloaded,m.instance.exportText);assert.match(downloaded,/Arroz #1\nfin/)
  await new Promise(r=>setTimeout(r,1100));assert.equal(revoked,clicked)
 }finally{m.close();globalThis.document=originalDocument;URL.revokeObjectURL=originalRevoke}
})
