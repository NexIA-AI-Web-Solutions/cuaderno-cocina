// Mounts the real native SFC script/template with explicit widget/API boundaries.
import {readFileSync} from 'node:fs'
import assert from 'node:assert/strict'
import {parse,compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'
export {all,textOf,button,field,flush} from './functionalComponentHarness.mjs'
import {moduleUrl,flush} from './functionalComponentHarness.mjs'
let sequence=0
export async function mountNative(filename,initialProps={},transport=()=>({count:0,results:[]}),options={}){
 const id=++sequence,calls=[],preferences=Vue.reactive({defaultUnitObj:{id:1,name:'kg'},deviceSettings:{general_tableItemsPerPage:10,search_viewMode:'table',search_itemsPerPage:10,search_visibleFilters:[]},...options.preferences});
 globalThis.__nativeKitchen??=new Map();globalThis.__nativeKitchen.set(id,{transport,calls,preferences});
 const vue=JSON.stringify(import.meta.resolve('vue'));
 const api=moduleUrl(`export class ApiApi{constructor(){return new Proxy(this,{get:(_,method)=>(...args)=>{const state=globalThis.__nativeKitchen.get(${id});state.calls.push({method,args});return Promise.resolve().then(()=>state.transport(method,...args))}})}}`);
 const store=moduleUrl(`export const ErrorMessageType={FETCH_ERROR:1,CREATE_ERROR:2,UPDATE_ERROR:3};export const PreparedMessage={CREATE_SUCCESS:1,UPDATE_SUCCESS:2};export const useMessageStore=()=>({addError(){},addPreparedMessage(){}});export const useUserPreferenceStore=()=>globalThis.__nativeKitchen.get(${id}).preferences;`);
 const i18n=moduleUrl(`export const useI18n=()=>({t:key=>key,n:x=>String(x)});`);
 const widget=moduleUrl(`import {defineComponent,h,ref} from ${vue};export const W=defineComponent({inheritAttrs:false,props:['modelValue','model','label'],emits:['update:modelValue'],setup:(p,c)=>()=>h('model-select',{...c.attrs,...p,label:p.label||p.model,'onUpdate:modelValue':v=>c.emit('update:modelValue',v)},[c.slots.default?.(),c.slots.append?.(),c.slots['append-inner']?.()])});export const VSelect=W,VTextField=W,VNumberInput=W,VDataTable=W,VDateInput=W;export const useDisplay=()=>({mdAndUp:ref(true),smAndDown:ref(${options.mobile === true})});export default W;`);
 const route=moduleUrl(`import {ref} from ${vue};export const useRouteQuery=(_key,value)=>ref(value);export const useRouter=()=>({push(){}});export const useDebouncedSearch=()=>{const query=ref('');return {inputValue:query,debouncedValue:query,signal:ref(undefined),flush(){},reset(){query.value=''}}};`);
 const util=moduleUrl(`export const ingredientToString=x=>[x.amount,x.unit?.name,x.food?.name].filter(Boolean).join(' ');export const boolOrUndefinedTransformer=x=>x;export const numberOrUndefinedTransformer=x=>x;export const routeQueryDateTransformer=x=>x;export const stringToBool=x=>x;export const toNumberArray=x=>x;`);
 const noop=moduleUrl(`import {h} from ${vue};export default {inheritAttrs:false,setup:(_,c)=>()=>h('component-stub',c.attrs,[c.slots.default?.(),c.slots.append?.(),c.slots['append-inner']?.()])};`);
 const model=moduleUrl(`import W from ${JSON.stringify(noop)};export const getGenericModelFromString=name=>({model:{editorComponent:W,localizationKey:name}});`);
 const inventory=moduleUrl(`export const inventoryRequests=()=>({override:()=>({}),complete(){},key:()=>''});`);
 const fetchApi=moduleUrl(`export const cuadernoFetch=(path,options)=>Promise.resolve({ok:true,status:200,data:{}});export const readJson=async r=>r;`);
 const forms=moduleUrl(ts.transpileModule(readFileSync(new URL('./forms.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText);
 const file=new URL(filename,import.meta.url),{descriptor,errors}=parse(readFileSync(file,'utf8'));assert.deepEqual(errors,[]);
 let source=ts.transpileModule(compileScript(descriptor,{id:'native-'+id,inlineTemplate:true,templateOptions:{compilerOptions:{hoistStatic:false}}}).content,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
 source=source.replace(/from (["'])([^"']+)\1/g,(_,q,name)=>{let url;if(name==='vue'||name==='luxon')url=import.meta.resolve(name);else if(name==='@/openapi')url=api;else if(name.includes('/stores/'))url=store;else if(name==='vue-i18n')url=i18n;else if(name.startsWith('vuetify'))url=widget;else if(name.includes('/VModelSelect')||name.includes('/ModelSelect'))url=widget;else if(name==='vue-router'||name==='@vueuse/router'||name.includes('useDebouncedSearch'))url=route;else if(name.includes('/utils/'))url=util;else if(name==='@/types/Models')url=model;else if(name==='@/cuaderno/inventoryRequests')url=inventory;else if(name==='@/cuaderno/api')url=fetchApi;else if(name==='@/cuaderno/forms')url=forms;else if(name.endsWith('.vue'))url=noop;else assert.fail(name);return `from ${JSON.stringify(url)}`});
 const component=(await import(moduleUrl(source))).default;
 const renderer=Vue.createRenderer({createElement:type=>({type,props:{},children:[],parent:null}),createText:text=>({type:'#text',text,props:{},children:[],parent:null}),createComment:text=>({type:'#comment',text,props:{},children:[],parent:null}),setText:(n,t)=>n.text=t,setElementText:(n,t)=>n.children=[{type:'#text',text:t,props:{},children:[],parent:n}],parentNode:n=>n.parent,nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1]||null,insert(n,p,a=null){if(n.parent)n.parent.children.splice(n.parent.children.indexOf(n),1);n.parent=p;const i=a?p.children.indexOf(a):-1;if(i<0)p.children.push(n);else p.children.splice(i,0,n)},remove(n){if(n.parent)n.parent.children.splice(n.parent.children.indexOf(n),1);n.parent=null},patchProp:(n,k,o,v)=>n.props[k]=v,setScopeId(){},insertStaticContent:()=>assert.fail('Static disabled')});
 const props=Vue.reactive(initialProps),root={type:'root',props:{},children:[],parent:null},app=renderer.createApp({setup:()=>()=>Vue.h(component,props)});
 const tags=new Set([...readFileSync(file,'utf8').matchAll(/<(v-[a-z-]+|router-link)\b/g)].map(m=>m[1]));
 for(const tag of tags)app.component(tag,Vue.defineComponent({inheritAttrs:false,props:['modelValue','items','headers','label','disabled','loading','persistent'],emits:['update:modelValue','update:options'],setup(p,c){return()=>{if(tag==='v-dialog'&&!p.modelValue)return null;const children=[c.slots.default?.(),c.slots.append?.(),c.slots.subtitle?.()];if(tag==='v-data-table-server')for(const item of p.items||[])for(const key of Object.keys(c.slots).filter(k=>k.startsWith('item.')))children.push(c.slots[key]?.({item}));return Vue.h(tag==='v-btn'?'button':tag,{...c.attrs,...p,'onUpdate:modelValue':v=>c.emit('update:modelValue',v),'onUpdate:options':v=>c.emit('update:options',v)},children)}}}));
 app.config.globalProperties.$t=k=>k;app.config.globalProperties.$n=x=>String(x);globalThis.window??={scrollTo(){}};
 app.mount(root);await flush();return{root,props,calls,preferences,close(){app.unmount();globalThis.__nativeKitchen.delete(id)}};
}
