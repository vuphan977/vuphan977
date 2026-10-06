const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {go}=require('./navigation.cjs');

(async()=>{
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({viewport:{width:412,height:915},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'});
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(12000);
  const url=process.env.TEST_URL||'http://127.0.0.1:3010';
  const manifestResponse=await context.request.get(url+'/manifest.webmanifest');
  assert.equal(manifestResponse.status(),200);
  assert.match(manifestResponse.headers()['content-type'],/manifest\+json/);
  const manifest=await manifestResponse.json();assert.equal(manifest.display,'standalone');assert.equal(manifest.scope,'/');
  for(const icon of manifest.icons){const r=await context.request.get(url+icon.src);const bytes=await r.body();assert.equal(r.status(),200);assert.equal(bytes.readUInt32BE(16),Number(icon.sizes.split('x')[0]));}
  await page.goto(url);
  await page.locator('#auth-toggle').click();await page.locator('#auth [name=name]').fill('Mobile QA owner');await page.locator('#auth [name=email]').fill('mobile-'+Date.now()+'@example.com');await page.locator('#auth [name=password]').fill('synthetic-mobile-password');await page.locator('#auth-submit').click();await page.locator('main').waitFor({state:'visible'});
  await page.locator('#mobile-nav').waitFor({state:'visible'});assert.equal(await page.locator('#mobile-nav button').count(),5);
  for(const width of [320,390,412]){await page.setViewportSize({width,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile layout must fit '+width);}
  await go(page,'Phòng');await page.locator('#primary').click();assert.equal(await page.locator('#fields').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);await page.locator('#fields [name=name]').fill('Mobile.1');await page.locator('#fields [name=rent]').fill('3000000');await page.locator('#form [type=submit]').click();await page.locator('#modal').waitFor({state:'hidden'});
  await go(page,'Dữ liệu');assert.ok((await page.locator('#title').innerText()).includes('Dữ liệu'));assert.equal(await page.locator('#mobile-menu').isVisible(),false);
  await page.locator('header [data-install-app]').click();await page.locator('#install-dialog').waitFor({state:'visible'});assert.match(await page.locator('#install-instructions').innerText(),/Chrome.*Android/);await page.locator('#install-close').click();
  // Test the install affordance without pretending a headless browser installed an OS app.
  await page.evaluate(()=>{const event=new Event('beforeinstallprompt',{cancelable:true});event.prompt=async()=>{window.prompted=true};event.userChoice=Promise.resolve({outcome:'dismissed'});window.dispatchEvent(event)});
  await page.locator('header [data-install-app]').click();assert.ok(await page.evaluate(()=>window.prompted));
  await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));
  const cacheURLs=await page.evaluate(async()=>{const urls=[];for(const name of await caches.keys()){const cache=await caches.open(name);urls.push(...(await cache.keys()).map(r=>new URL(r.url).pathname))}return urls});
  assert.ok(cacheURLs.includes('/offline.html'));assert.ok(cacheURLs.every(path=>!path.startsWith('/api/')&&path!=='/'));
  await go(page,'Phòng');await page.locator('#primary').click();await page.locator('#fields [name=name]').fill('Must not save offline');await page.locator('#fields [name=rent]').fill('3000000');
  await context.setOffline(true);await page.locator('#connection-status').waitFor({state:'visible'});await page.locator('#form [type=submit]').click();assert.ok(await page.locator('#modal').isVisible());await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Đang mất mạng'));
  await page.reload();await page.locator('h1').waitFor();assert.match(await page.locator('h1').innerText(),/Chưa có kết nối/);assert.equal(await page.locator('#content').count(),0);assert.ok(!(await page.locator('body').innerText()).includes('Mobile QA owner'));
  await context.setOffline(false);await page.locator('#retry').click();await page.locator('#mobile-nav').waitFor({state:'visible'});await go(page,'Phòng');assert.equal(await page.locator('.room').filter({hasText:'Must not save offline'}).count(),0);assert.equal(await page.locator('.room').filter({hasText:'Mobile.1'}).count(),1);
  await page.screenshot({path:'artifacts/roomly-mobile-rooms.png',fullPage:false});await page.locator('#mobile-menu-open').click();await page.locator('#mobile-logout').click();await page.locator('#auth').waitFor({state:'visible'});assert.equal(await page.locator('#mobile-nav').isVisible(),false);
  const ios=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'});
  const iphone=await ios.newPage();await iphone.goto(url);await iphone.locator('#auth [data-install-app]').click();assert.match(await iphone.locator('#install-instructions').innerText(),/Safari.*Chia sẻ.*Màn hình chính/);
  await page.screenshot({path:'artifacts/mobile-install-login.png',fullPage:true});assert.deepEqual(errors,[]);
  console.log('Mobile/PWA browser passed: manifest and PNG icons, 320–412px layout, bottom tabs/menu, touch form, Android/iPhone install guidance, prompt action, public-only cache, offline save protection, offline launch/reconnect and logout. OS/store installation was not tested.');
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
