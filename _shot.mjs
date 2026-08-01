import { chromium } from 'playwright';
const b = await chromium.launch();
const pg = await b.newPage({ viewport:{width:390,height:1200}, deviceScaleFactor:2 });
await pg.goto('file:///Users/stevenrhodes/caney/out/caney.html');
await pg.waitForTimeout(1500);
await pg.evaluate(()=>document.querySelectorAll('.secbody').forEach(e=>e.classList.add('open')));
for (const c of ['power','wade']) {
  await pg.evaluate(k=>setCraft(k), c);
  await pg.waitForTimeout(300);
  await pg.evaluate(()=>{const r=[...document.querySelectorAll('#cal .wkrow')];
    const t=r.find(x=>/Tue/.test(x.textContent))||r[3];
    if(!document.getElementById('cs'+t.dataset.di).classList.contains('open'))t.click();});
  await pg.waitForTimeout(300);
  await pg.locator('#cal').screenshot({path:`/tmp/cal-${c}.png`});
}
await b.close();
