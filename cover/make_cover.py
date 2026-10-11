# -*- coding: utf-8 -*-
"""
B站视频封面渲染脚本
------------------
用 Playwright + 系统 Chrome 把 cover_a.html / cover_b.html
渲染成 1146x717（2x 输出 2292x1434）的 PNG 封面。

用法：
    python make_cover.py
输出（项目根目录）：
    视频封面_白底版.png
    视频封面_红底版.png
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

W, H = 1146, 717          # B站官方推荐封面尺寸
SCALE = 2                 # 2x 输出，更清晰

JOBS = [
    ("cover_a.html", "视频封面_白底版.png"),
    ("cover_b.html", "视频封面_红底版.png"),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要 playwright：pip install playwright")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME,
            args=["--hide-scrollbars", "--allow-file-access-from-files"],
        )
        for src, out in JOBS:
            src_path = HERE / src
            if not src_path.exists():
                print(f"跳过（不存在）：{src}")
                continue
            page = browser.new_page(viewport={"width": W, "height": H},
                                    device_scale_factor=SCALE)
            page.goto(src_path.as_uri(), wait_until="load")
            page.evaluate("document.fonts && document.fonts.ready")
            page.wait_for_timeout(700)   # 等 emoji / 字体完成渲染
            dst = ROOT / out
            page.screenshot(path=str(dst))
            page.close()
            size_kb = dst.stat().st_size / 1024
            print(f"OK  {out}  ({W*SCALE}x{H*SCALE}, {size_kb:.0f} KB)")
        browser.close()


if __name__ == "__main__":
    main()
