/* Run from the repo root against the isolated local server, never production. */
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('assert');
const origin='http://127.0.0.1:8123';
const shots=path.join(process.cwd(),'v2/static/screens');
const qa=process.env.SUYING_QA_DIR||'/tmp/suying-knowledge-qa';
const demo={account:{username:'示範帳號',status:'已開通',trial_available:false},csrf:'local-demo',member:'正式會員｜示範帳號',access:true,admin:false,road:[],active:false,favorites:[],bingo_featured:false,pending:false,campaigns:[]};
(async()=>{
 fs.mkdirSync(shots,{recursive:true});fs.mkdirSync(qa,{recursive:true});
 const loaded=process.env.SUYING_CHROMIUM_PACKAGE?require(process.env.SUYING_CHROMIUM_PACKAGE):null;
 const bundled=loaded?.default||loaded;
 const browser=await chromium.launch({headless:true,...(bundled?{executablePath:await bundled.executablePath(),args:bundled.args}: {})});
 // Only local preview data is substituted; screenshots preserve the real portal DOM and CSS.
 const capture=await browser.newPage({viewport:{width:390,height:740},deviceScaleFactor:2,bypassCSP:true});
 const fontDir=process.env.SUYING_FONT_DIR;
 let fontCSS='';
 if(fontDir)fontCSS=fs.readFileSync(path.join(fontDir,'400.css'),'utf8').replace(/url\(([^)]+)\)/g,(_,file)=>`url(data:font/woff2;base64,${fs.readFileSync(path.join(fontDir,file.replaceAll("'",'').replaceAll('"',''))).toString('base64')})`)+`body{font-family:'Noto Sans TC',sans-serif!important}`;
 await capture.route('**/api/portal',r=>r.fulfill({json:demo}));
 await capture.route('**/api/command',r=>r.fulfill({json:{replies:[]}}));
 await capture.route('**/api/539/overview',r=>r.fulfill({json:{target_date:'2026-10-22',previous:null,latest:null,prediction:null,status:'示範介面 · 請以登入後當期資料為準'}}));
 for(const mode of ['baccarat','539','bingo']){
   await capture.goto(origin+'/#'+mode);await capture.waitForSelector(`#main[data-page="${mode}"]`);
   if(fontCSS){await capture.addStyleTag({content:fontCSS});await capture.evaluate(()=>document.fonts.ready)}
   if(mode==='baccarat'){
     await capture.locator('section.panel').filter({has:capture.locator('#road-image')}).screenshot({path:path.join(shots,mode+'.jpg'),type:'jpeg',quality:76,style:'.top,.bottom{visibility:hidden!important}'});
   }else{
     const box=await capture.locator('#main').boundingBox();
     await capture.screenshot({path:path.join(shots,mode+'.jpg'),type:'jpeg',quality:76,clip:{x:0,y:box.y,width:390,height:510},style:'.top,.bottom{visibility:hidden!important}'});
   }
 }
 const errors=[];
 await capture.unrouteAll();
 const page=capture;
 page.on('pageerror',e=>errors.push(e.message));
 for(const width of [390,320,1440]){
   await page.setViewportSize({width,height:950});
   for(const route of ['/','/discover','/guide/baccarat','/guide/539','/guide/bingo','/learn','/learn/reading-signals']){
     const response=await page.goto(origin+route);assert.equal(response.status(),200,route);
     if(route==='/')await page.waitForSelector('.home-hero');
     if(fontCSS){await page.addStyleTag({content:fontCSS});await page.evaluate(()=>document.fonts.ready)}
     await page.locator('img').evaluateAll(imgs=>Promise.all(imgs.map(i=>i.complete?Promise.resolve():new Promise(resolve=>{i.onload=resolve;i.onerror=resolve}))));
     const sizes=await page.evaluate(()=>({page:document.documentElement.scrollWidth,view:innerWidth}));
     assert(sizes.page<=sizes.view,`horizontal overflow at ${width} ${route}: ${JSON.stringify(sizes)}`);
     const broken=await page.locator('img').evaluateAll(imgs=>imgs.filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.src));
     assert.equal(broken.length,0,`broken images ${broken}`);
     if(width!==320)await page.screenshot({path:path.join(qa,`${width}-${route.replaceAll('/','_')||'home'}.png`),fullPage:true});
   }
   await page.goto(origin+'/');await page.waitForSelector('.home-hero');
   await page.getByRole('button',{name:'選擇功能'}).click();
   assert(!page.url().includes('start-modes'),'home anchor must not be treated as a portal route');
   await page.goto(origin+'/learn');
   await page.getByRole('searchbox').fill('4MB');await page.getByRole('button',{name:'搜尋',exact:true}).click();
   await page.waitForURL('**/learn?*');assert(await page.getByRole('heading',{name:'截圖怎麼傳，才比較容易核對？'}).isVisible());
   assert.equal(await page.locator('.article-card').count(),1);
   await page.goto(origin+'/discover');
   await page.getByText('需要先登入才能看介紹嗎？',{exact:true}).click();
   assert(await page.getByText('產品介紹與參考文章可以直接閱讀。',{exact:false}).isVisible());
   await page.getByRole('link',{name:'參考資訊',exact:true}).first().click();await page.waitForURL('**/learn');
 }
 assert.deepEqual(errors,[]);
 await capture.close();await browser.close();console.log('PASS: actual-interface screenshots; public home/3 mode pages/library/article at 320,390,1440px; no overflow/broken images; search, FAQ and navigation.');
})().catch(e=>{console.error(e);process.exitCode=1});
