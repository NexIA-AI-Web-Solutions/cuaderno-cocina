import {chromium} from '../../../tests/cuaderno/e2e/node_modules/@playwright/test/index.mjs'
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
const root=fileURLToPath(new URL('.',import.meta.url)), out=root+'generated/'
const data=JSON.parse(readFileSync(root+'comparison.json','utf8'))
const browser=await chromium.launch({executablePath:process.env.CUADERNO_BROWSER_EXECUTABLE || '/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1000}})
const errors=[];page.on('pageerror',error=>errors.push(error.message))
try {
 await page.goto('http://127.0.0.1:18879/print.html',{waitUntil:'networkidle'})
 await page.evaluate(()=>document.fonts.ready)
 await page.emulateMedia({media:'print'})
 const pages=await page.locator('.pdf-page').evaluateAll(nodes=>nodes.map(el=>{const c=el.querySelector('.content').getBoundingClientRect(),f=el.querySelector('footer').getBoundingClientRect();return {page:el.dataset.page,contentBottom:c.bottom,footerTop:f.top,width:el.clientWidth,scrollWidth:el.scrollWidth,overflow:c.bottom>f.top-6 || el.scrollWidth>el.clientWidth+1}}))
 if(pages.some(p=>p.overflow))throw Error('Print overflow: '+JSON.stringify(pages))
 await page.pdf({path:out+'Cuaderno-Cocina-Planes.pdf',preferCSSPageSize:true,printBackground:true,tagged:true})
 for(let n=0;n<4;n++)await page.locator('.pdf-page').nth(n).screenshot({path:out+`pdf-page-${n+1}.png`})
 await page.emulateMedia({media:'screen'})
 await page.goto('http://127.0.0.1:18879/',{waitUntil:'networkidle'})
 const featureCount=await page.locator('[data-feature]').count()
 if(featureCount!==38)throw Error('Missing comparison rows')
 for(const g of data.groups)for(const r of g.rows){const actual=await page.locator(`[data-feature="${r.id}"] td`).allTextContents();for(let i=0;i<3;i++)if(actual[i].replace('✓','').trim()!==(r.values[i]??'—'))throw Error('Edition mismatch '+r.id)}
 await page.locator('.wrap').screenshot({path:out+'comparison-desktop.png'})
 await page.setViewportSize({width:390,height:844})
 const mobile=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,table:document.querySelector('.plan-scroll').scrollWidth,frame:document.querySelector('.plan-scroll').clientWidth}))
 if(mobile.document>mobile.width || mobile.table<=mobile.frame)throw Error('Mobile overflow handling failed')
 await page.locator('.plan-intro').scrollIntoViewIfNeeded()
 await page.screenshot({path:out+'comparison-mobile.png'})
 if(errors.length)throw Error(errors.join('\n'))
 writeFileSync(out+'validation.json',JSON.stringify({featureCount,pages,mobile,browserErrors:errors,pdfPages:4},null,2)+'\n')
 console.log('PASS: 38 matching rows, 4 pages without overflow, mobile and desktop.')
}finally{await browser.close()}
