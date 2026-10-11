# -*- coding: utf-8 -*-
"""一次性视觉验收：起 中台(18081) + 后端(18082) + 前端(5173) -> 多状态截图 -> 全部关闭。

沙箱限制：从 shell 起的进程在工具调用结束会被回收，所以必须一个进程内跑完。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\software\PycharmProjects\customer-service-backend")
OUT = ROOT / ".workbuddy" / "_shots2"
OUT.mkdir(parents=True, exist_ok=True)

PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
COMMERCE_PY = str(ROOT / "external" / "ecommerce-service-backend" / ".venv" / "Scripts" / "python.exe")
NODE = r"C:\Users\23329\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
VITE = str(ROOT / "external" / "customer-service-frontend" / "node_modules" / "vite" / "bin" / "vite.js")

log = []
procs = []


def L(msg):
    log.append(str(msg))


# 清掉沙箱出网代理，否则子进程会把请求发去 127.0.0.1:62982
ENV = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "no_proxy", "all_proxy")}


def spawn(name, cmd, cwd, logname):
    f = io.open(OUT / logname, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(cmd, cwd=str(cwd), env=ENV, stdout=f, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    procs.append((name, p, f))
    L("start %s pid=%s" % (name, p.pid))
    return p


def probe(url, timeout=2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def wait_port(url, label, limit=60):
    for _ in range(limit * 2):
        s = probe(url)
        if isinstance(s, int):
            L("ok %s -> %s (%s)" % (label, s, url))
            return True
        time.sleep(0.5)
    L("FAIL %s 未就绪 (%s)" % (label, url))
    return False


try:
    spawn("commerce", [COMMERCE_PY, "main.py"], ROOT / "external" / "ecommerce-service-backend", "_commerce.log")
    spawn("backend", [PY, "main.py"], ROOT, "_backend.log")
    ok_c = wait_port("http://127.0.0.1:18081/docs", "中台18081", 40)
    ok_b = wait_port("http://127.0.0.1:18082/health", "后端18082", 40)

    spawn("frontend", [NODE, VITE, "--host", "localhost", "--port", "5173"],
          ROOT / "external" / "customer-service-frontend", "_vite.log")
    ok_f = wait_port("http://localhost:5173/", "前端5173", 60)

    if not (ok_c and ok_b and ok_f):
        L("有服务未起来，仍尝试截图")

    # ---- 端到端接口复测 ----
    for u in ("http://localhost:5173/commerce/users/u1001/orders",
              "http://localhost:5173/api/chat/history?sender_id=u1001"):
        L("probe %s -> %s" % (u, probe(u, 6)))

    # 商品/订单封面用的是外链 placehold.co：沙箱里只有走代理才通，
    # 而 Chrome 不认 http_proxy 环境变量，必须显式 --proxy-server，否则缩略图全空。
    proxy_url = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    launch_kw = {"executable_path": CHROME,
                 "args": ["--enable-unsafe-swiftshader", "--use-gl=angle",
                          "--use-angle=swiftshader"]}
    if proxy_url:
        # bypass 必须带上，否则连 localhost:5173 也会被塞进代理，页面直接白屏
        launch_kw["proxy"] = {"server": proxy_url, "bypass": "localhost,127.0.0.1,::1"}
        launch_kw["args"].append("--ignore-certificate-errors")
        L("browser proxy = %s (bypass localhost)" % proxy_url)

    from playwright.sync_api import sync_playwright

    console = []
    netfail = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kw)
        for w, h, tag in ((1680, 1000, "1680"), (1280, 900, "1280")):
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.on("console", lambda m: console.append("[%s] %s" % (m.type, m.text)))
            page.on("pageerror", lambda e: console.append("[pageerror] %s" % e))
            page.on("requestfailed", lambda r: netfail.append("%s %s" % (r.url, r.failure)))
            page.on("response", lambda r: netfail.append("HTTP %s %s" % (r.status, r.url))
                    if r.status >= 400 else None)

            page.goto("http://localhost:5173/", wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            page.screenshot(path=str(OUT / ("01-history-%s.png" % tag)))

            if tag == "1680":
                # 欢迎态：清空 sender
                inp = page.locator(".controls input")
                inp.fill("")
                page.wait_for_timeout(2000)
                page.screenshot(path=str(OUT / "02-welcome.png"))
                # 悬停态
                if page.locator(".welcome-chip").count():
                    page.locator(".welcome-chip").first.hover()
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(OUT / "03-chip-hover.png"))
                # 右侧商品 tab
                inp.fill("u1001")
                page.wait_for_timeout(5000)
                tabs = page.locator(".tab-button")
                if tabs.count() > 1:
                    tabs.nth(1).click()
                    page.wait_for_timeout(1200)
                    page.screenshot(path=str(OUT / "04-products.png"))
                # 点「发送订单」看对象卡片
                tabs.nth(0).click()
                page.wait_for_timeout(800)
                send = page.locator(".sidebar-card .secondary-button")
                if send.count():
                    send.first.click()
                    page.wait_for_timeout(12000)
                    page.screenshot(path=str(OUT / "05-object-card.png"))
                page.screenshot(path=str(OUT / "06-fullpage.png"), full_page=True)
            else:
                # 单栏堆叠模式：滚下去看数字人卡是否已收成紧凑块
                page.evaluate("window.scrollTo(0, 900)")
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / "07-stacked-scroll.png"))
            page.close()
        browser.close()

    L("--- console ---")
    for c in console[:60]:
        L(c)
    L("--- net >=400 / failed ---")
    for n in dict.fromkeys(netfail):
        L(n)
finally:
    for name, p, f in procs:
        try:
            p.terminate()
            p.wait(timeout=8)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        try:
            f.close()
        except Exception:
            pass
        L("stop %s" % name)

with io.open(OUT / "runlog.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(log) + "\n")
print("DONE")
