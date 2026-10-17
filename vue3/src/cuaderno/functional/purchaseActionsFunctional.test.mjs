import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle} from './functionalHarness.mjs'

function setup(transport=async()=>({ok:true,status:200,data:[]})) {
    const calls=[]
    const h=component('cuaderno/components/PurchasingPanel.vue', ['confirmation','confirmationError','confirming','requestPurchaseAction','dismissPurchaseAction','confirmPurchaseAction','orders','receipt','receive'], {globals:{
        withDefaults:p=>p,defineProps:()=>({canOperate:true}),reactive:x=>x,
        inventoryRequests:()=>({key:()=> 'test-key',complete(){}}),
        cuadernoFetch:(url,options={})=>{calls.push({url,options});return transport(url,options)},readJson:async x=>x,
        apiError:()=> 'Conflicto de existencias',decimalInput:x=>Number(x)>0?x:null,
        purchaseOrders:x=>x,purchaseReceipts:x=>x,sameReceiptDraft:()=>false,
    }})
    return {...h.exposed,calls}
}
const order={id:8,food:21,household:3,unit:2,quantity:'10',received_quantity:'2',state:'ordered'}
const document={id:17,quantity:'2',movement:6,reversed_by:null}
test('reviewing or dismissing a receipt reversal never writes; confirmation submits once', async()=>{
    const response=deferred(),s=setup((url,options)=>options.method==='POST'?response.promise:Promise.resolve({ok:true,status:200,data:[]}))
    s.requestPurchaseAction('reverse',order,document)
    assert.equal(s.calls.length,0)
    s.dismissPurchaseAction();assert.equal(s.confirmation.value,null)
    s.requestPurchaseAction('reverse',order,document)
    const pending=s.confirmPurchaseAction();await settle()
    await s.confirmPurchaseAction();s.dismissPurchaseAction()
    assert.equal(s.calls.filter(c=>c.options.method==='POST').length,1)
    assert.equal(s.calls[0].url,'/api/cuaderno/purchase-receipts/17/reverse/')
    assert.ok(s.confirmation.value)
    response.resolve({ok:true,status:200,data:{}});await pending
    assert.equal(s.confirmation.value,null)
})
test('cancelling an order requires confirmation and a rejected action stays recoverable', async()=>{
    const s=setup(async()=>({ok:false,status:409,data:{}}))
    s.requestPurchaseAction('cancel',order)
    assert.equal(s.calls.length,0)
    await s.confirmPurchaseAction()
    assert.equal(JSON.parse(s.calls[0].options.body).action,'cancel')
    assert.ok(s.confirmation.value)
    assert.match(s.confirmationError.value,/Conflicto/)
    assert.equal(s.confirming.value,false)
})
test('wrong food or household is rejected before attempting a receipt write', async()=>{
    const s=setup();s.receipt.quantity='2'
    for(const entry of [{id:1,food:{id:22},inventoryLocation:{household:{id:3}}},{id:2,food:{id:21},inventoryLocation:{household:{id:4}}}]) {
        s.receipt.entry=entry;await s.receive(order)
    }
    assert.equal(s.calls.length,0)
})
