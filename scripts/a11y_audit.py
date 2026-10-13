"""
ممیزی دسترس‌پذیری با axe-core روی صفحه‌های اصلی (روشن/تیره × موبایل/دسکتاپ؛ مهمان، عضو، مدیر).
نیازها: pip install playwright (+ مرورگر)، npm i axe-core، سرور در حال اجرا با داده‌ی seed_demo.
  python scripts/a11y_audit.py          # خروجی «NO VIOLATIONS» یعنی همه‌ی صفحه‌ها تمیزن
تنظیم: AXE_PATH (پیش‌فرض /tmp/lh/node_modules/axe-core/axe.min.js)، CHROME_PATH، BASE_URL.
"""
import asyncio
from playwright.async_api import async_playwright
import os
AX=os.environ.get('AXE_PATH','/tmp/lh/node_modules/axe-core/axe.min.js')
CHROME=os.environ.get('CHROME_PATH','/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PAGES=[('guest','/authors/'),('guest','/publishers/'),('member','/accounts/points/'),('member','/exchanges/'),('guest','/books/'),('guest','/books/12/'),('guest','/'),('guest','/accounts/login/'),('member','/books/new/'),('member','/books/bulk/'),('member','/books/12/'),('member','/books/mine/'),('member','/accounts/stats/'),('staff','/panel/'),('staff','/panel/users/'),('member','/books/shelf/'),('member','/books/shelf/add/'),('guest','/story/?book=12'),('member','/accounts/u/neda/'),('member','/accounts/feed/'),('guest','/clubs/'),('member','/books/shelf/stats/'),('member','/books/highlights/'),('member','/books/shelf/export/?print=1')]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME)
        B=os.environ.get('BASE_URL','http://127.0.0.1:8765'); total={}
        for scheme in ('light','dark'):
            for vp,(w,h) in (('mobile',(390,844)),('desktop',(1280,900))):
                ctxs={}
                for role,user in (('guest',None),('member','neda'),('staff','boss')):
                    ctx = await b.new_context(viewport={'width':w,'height':h}, color_scheme=scheme); pg=await ctx.new_page()
                    if user:
                        await pg.goto(B+'/accounts/login/'); await pg.fill('[name=username]',user); await pg.fill('[name=password]','demo12345'); await pg.press('[name=password]','Enter'); await pg.wait_for_load_state()
                    ctxs[role]=pg
                for role,url in PAGES:
                    pg=ctxs[role]
                    await pg.goto(B+url); await pg.wait_for_load_state('networkidle')
                    await pg.add_script_tag(path=AX)
                    res = await pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,t:v.nodes[0].target.join(' '),h:v.nodes[0].html.slice(0,110)})))")
                    for v in res:
                        total.setdefault((v['id'],v['impact']),[]).append((scheme,vp,url,v['n'],v['t'],v['h']))
        for (vid,imp),items in sorted(total.items()):
            print(vid,imp,len(items)); 
            for it in items[:3]: print('   ',it)
        if not total: print('NO VIOLATIONS')
        await b.close()
asyncio.run(main())
