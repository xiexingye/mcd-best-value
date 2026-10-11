"""
麦门演示片 · 逐帧渲染 + 编码
用法：
    python render_video.py            # 渲染全部 60 秒
    python render_video.py 20 25      # 只渲染 20-25 秒（调试用）
"""
import os, sys, io, json, time, subprocess, shutil, tempfile
from pathlib import Path

ROOT = Path(r"C:\Users\AppleRepair\Desktop\mcd-best-value")
RENDER_DIR = ROOT / "render"
FRAMES_DIR = RENDER_DIR / "_frames"
OUT_MP4 = ROOT / "麦门省钱助手_演示片.mp4"
AUDIO = ROOT / "audio" / "narration.mp3"

FPS = 30
DURATION = 44.30        # 与 audio/narration.mp3 严格同步（音频 44.35s）
W, H = 1920, 1080

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

sys.path.insert(0, str(Path(sys.executable).parent))
from imageio_ffmpeg import get_ffmpeg_exe

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("需要 playwright：pip install playwright && playwright install chromium")
    sys.exit(1)


def main():
    a0 = float(sys.argv[1]) if len(sys.argv) > 2 else 0
    a1 = float(sys.argv[2]) if len(sys.argv) > 2 else DURATION

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    url = (RENDER_DIR / "renderer.html").as_uri()

    total_frames = int(round((a1 - a0) * FPS))
    print(f"渲染 {a0}s ~ {a1}s，共 {total_frames} 帧 ({FPS}fps, {W}x{H})")

    t_start = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME,
            args=["--allow-file-access-from-files", "--hide-scrollbars",
                  "--force-device-scale-factor=1", "--disable-lcd-text"],
        )
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)
        page.goto(url, wait_until="load")
        page.wait_for_function("window.__RENDER_READY__ === true", timeout=20000)
        # 等字体加载
        page.evaluate("document.fonts && document.fonts.ready")

        canvas = page.locator("#cv")
        for i in range(total_frames):
            t = a0 + i / FPS
            page.evaluate("(t) => window.renderFrame(t)", t)
            canvas.screenshot(path=str(FRAMES_DIR / f"f{i:05d}.png"))
            if i % 60 == 0:
                el = time.time() - t_start
                pct = i / total_frames * 100
                eta = (el / max(i, 1)) * (total_frames - i)
                print(f"  {i}/{total_frames} ({pct:.1f}%) 已用 {el:.0f}s  预计还需 {eta:.0f}s",
                      flush=True)
        browser.close()

    print(f"抓帧完成，用时 {time.time()-t_start:.0f}s")
    encode(total_frames)
    cleanup()


def encode(n_frames):
    """用 imageio-ffmpeg 把帧序列 + 音频编成 MP4
    -frames:v 限制只编码本次抓取的帧数，避免目录里残留的旧帧混进视频"""
    ff = get_ffmpeg_exe()
    has_audio = AUDIO.exists()

    cmd = [
        ff, "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "f%05d.png"),
    ]
    if has_audio:
        cmd += ["-i", str(AUDIO)]

    cmd += [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-frames:v", str(n_frames),
        "-movflags", "+faststart",
    ]
    if has_audio:
        cmd += [
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-af", "apad",          # 音频不足时补静音
            "-shortest",
        ]
    cmd += [str(OUT_MP4)]

    print("编码中…")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("FFMPEG 失败：")
        print(r.stderr[-3000:])
        sys.exit(1)
    size = OUT_MP4.stat().st_size / 1024 / 1024
    print(f"✅ 完成：{OUT_MP4}  ({size:.1f} MB)")


def cleanup():
    """保留临时帧以便复用（不删除任何文件）"""
    n = len(list(FRAMES_DIR.glob("*.png"))) if FRAMES_DIR.exists() else 0
    print(f"临时帧保留在：{FRAMES_DIR}（{n} 张），可自行删除")


if __name__ == "__main__":
    main()
