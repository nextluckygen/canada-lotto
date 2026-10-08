"""One-off generator for the share image and favicon set (Draw Night style).

Usage (needs Playwright + Chrome + Pillow; not used by the nightly build):
    python tools/make_brand_assets.py
Writes assets/og/lottohelper-og.png (1200x630), assets/icons/icon-512.png, assets/icons/favicon-32.png,
apple-touch-icon.png (180x180) and favicon.ico (16/32/48) in the repo root.
"""
import os
import sys
from io import BytesIO

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = "file://" + os.path.join(ROOT, "assets", "fonts", "baloo2-latin.woff2")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")

BASE_CSS = """
@font-face { font-family: "Baloo 2"; font-weight: 400 800; src: url(%s) format("woff2"); }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: "Baloo 2", system-ui, sans-serif; }
.ball { --s:96px; --c:#64748B; width:var(--s); height:var(--s); border-radius:50%%; display:grid; place-items:center; position:relative;
  background: radial-gradient(circle at 30%% 25%%, rgba(255,255,255,.9) 0 5%%, rgba(255,255,255,0) 28%%),
              radial-gradient(circle at 50%% 115%%, rgba(0,0,0,.35), transparent 55%%), var(--c);
  box-shadow: inset -5px -7px 14px rgba(0,0,0,.28), 0 10px 24px rgba(0,0,0,.35); }
.ball span { background:#fff; color:#111827; border-radius:50%%; width:62%%; height:62%%; display:grid; place-items:center;
  font-weight:800; font-size:calc(var(--s)*.36); padding-top:.08em; }
.r1 { --c:#FACC15; } .r2 { --c:#2563EB; } .r3 { --c:#DC2626; } .r4 { --c:#15803D; } .r5 { --c:#7C3AED; } .r6 { --c:#BE185D; }
""" % FONT

OG_HTML = """<!doctype html><html><head><style>%s
.og { width:1200px; height:630px; color:#fff; position:relative; overflow:hidden; padding:64px 72px;
  background: radial-gradient(circle at 12%% 18%%, rgba(251,191,36,.22) 0 3px, transparent 4px) 0 0/58px 58px,
              radial-gradient(circle at 70%% 60%%, rgba(255,255,255,.10) 0 2px, transparent 3px) 0 0/42px 42px,
              linear-gradient(135deg, #0B1033 0%%, #312E81 58%%, #6D28D9 100%%); }
.badge { display:inline-block; background:#FBBF24; color:#0B1033; font-weight:800; letter-spacing:.06em; font-size:34px; padding:4px 22px; border-radius:16px; }
.dots { display:inline-flex; gap:8px; margin-left:16px; vertical-align:middle; }
.dots i { width:18px; height:18px; border-radius:50%%; display:block; }
h1 { font-size:72px; line-height:1.02; font-weight:800; margin-top:40px; letter-spacing:-.01em; }
h1 em { font-style:normal; color:#FBBF24; text-shadow:0 2px 24px rgba(251,191,36,.35); }
p { font-size:27px; color:#E0E7FF; margin-top:22px; white-space:nowrap; font-family: system-ui, sans-serif; }
.balls { position:absolute; right:64px; bottom:56px; display:flex; gap:14px; }
.foot { position:absolute; left:72px; bottom:58px; font-size:24px; color:#C7D2FE; font-family: system-ui, sans-serif; }
</style></head><body><div class="og">
<span class="badge">LOTTOHELPER.CA</span><span class="dots"><i style="background:#FACC15"></i><i style="background:#2563EB"></i><i style="background:#DC2626"></i><i style="background:#15803D"></i><i style="background:#7C3AED"></i></span>
<h1>Lotto Max &amp; 6/49<br><em>results, stats &amp; free tools</em></h1>
<p>Every draw since 1982 · Check my numbers · Hot &amp; cold stats · Odds calculator</p>
<div class="foot">Independent · Unofficial · No predictions</div>
<div class="balls"><div class="ball r1"><span>?</span></div><div class="ball r2"><span>?</span></div><div class="ball r3"><span>?</span></div><div class="ball r4"><span>?</span></div><div class="ball r5"><span>?</span></div></div>
</div></body></html>""" % BASE_CSS

ICON_HTML = """<!doctype html><html><head><style>%s
.ic { width:512px; height:512px; border-radius:112px; position:relative; overflow:hidden;
  background: linear-gradient(135deg, #0B1033 0%%, #312E81 70%%, #6D28D9 100%%); display:grid; place-items:center; }
.ic .ball { --s:400px; --c:#FBBF24; }
.ic .ball span { width:66%%; height:66%%; font-size:150px; letter-spacing:-.02em; color:#0B1033; padding-top:.1em; }
</style></head><body style="background:transparent"><div class="ic"><div class="ball"><span>LH</span></div></div></body></html>""" % BASE_CSS


def shot(page, html, w, h, selector):
    page.set_viewport_size({"width": w, "height": h})
    page.set_content(html)
    page.wait_for_timeout(300)
    page.evaluate("document.fonts.ready")
    return page.locator(selector).screenshot(omit_background=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--allow-file-access-from-files"])
        page = b.new_page()
        og = Image.open(BytesIO(shot(page, OG_HTML, 1200, 630, ".og"))).convert("RGB")
        icon = Image.open(BytesIO(shot(page, ICON_HTML, 512, 512, ".ic"))).convert("RGBA")
        b.close()
    og.save(os.path.join(ROOT, "assets", "og", "lottohelper-og.png"), optimize=True)
    icon.save(os.path.join(ROOT, "assets", "icons", "icon-512.png"), optimize=True)
    icon.resize((32, 32), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icons", "favicon-32.png"), optimize=True)
    apple = Image.new("RGB", (180, 180), "#0B1033")
    apple.paste(icon.resize((180, 180), Image.LANCZOS), (0, 0), icon.resize((180, 180), Image.LANCZOS))
    apple.save(os.path.join(ROOT, "apple-touch-icon.png"), optimize=True)
    icon.save(os.path.join(ROOT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    print("brand assets written")


if __name__ == "__main__":
    sys.exit(main())
