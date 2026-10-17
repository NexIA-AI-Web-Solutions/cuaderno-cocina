import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'

const source = readFileSync(new URL('../components/inputs/GlobalSearchDialog.vue', import.meta.url), 'utf8')
const script = stripTypeScriptTypes(source.split('<script setup lang="ts">')[1].split('</script>')[0], {mode: 'transform'}).replace(/^import .*$/gm, '')
function setup() {
    const box = value => ({value}), navigations = [], watchers = []
    const state = new Function('computed','onMounted','onUnmounted','ref','watch','useRouter','useDisplay','useI18n','useDebouncedSearch','document', `${script};return {dialog,searchQuery,flatRecipes,selectedResult,searchResults,handleKeydown,openAdvancedSearch}`)(
        fn => ({get value(){return fn()}}),()=>{},()=>{},box,(target,cb)=>watchers.push({target,cb}),()=>({push:to=>navigations.push(to)}),()=>({mobile:box(false)}),()=>({t:x=>x}),()=>({inputValue:box(''),debouncedValue:box(''),signal:box(undefined),reset(){}}),{getElementById:()=>null},
    )
    state.flatRecipes.value = [{id:7,name:'Arroz'},{id:8,name:'Sopa'}]
    return {...state,navigations,watchers}
}
const event = (key, id='id_global_search_input', extra={}) => ({key,target:{id},preventDefault(){this.prevented=true},...extra})

test('Enter on Close or Advanced never activates a recipe behind that button', () => {
    const s=setup();s.dialog.value=true;s.selectedResult.value=1
    s.handleKeydown(event('Enter','close-search'))
    assert.deepEqual(s.navigations,[])
    assert.equal(s.dialog.value,true)
})
test('arrows prevent page scrolling, stay in range and Enter opens the selected recipe', () => {
    const s=setup();s.dialog.value=true
    const down=event('ArrowDown');s.handleKeydown(down)
    assert.equal(down.prevented,true)
    assert.equal(s.selectedResult.value,1)
    s.handleKeydown(event('Enter'))
    assert.deepEqual(s.navigations,[{name:'RecipeViewPage',params:{id:7}}])
})
test('text composition does not accidentally navigate and Command-K opens search', () => {
    const s=setup();s.handleKeydown(event('k','', {metaKey:true}))
    assert.equal(s.dialog.value,true)
    s.handleKeydown(event('Enter','id_global_search_input',{isComposing:true}))
    assert.deepEqual(s.navigations,[])
})
test('advanced search keeps the current query and a new query resets selection', () => {
    const s=setup();s.dialog.value=true;s.selectedResult.value=1;s.searchQuery.value='Arroz'
    s.watchers.find(w=>w.target===s.searchQuery).cb()
    assert.equal(s.selectedResult.value,0)
    s.searchQuery.value='  Arroz  '
    s.openAdvancedSearch()
    assert.deepEqual(s.navigations,[{name:'SearchPage',query:{query:'Arroz'}}])
})
