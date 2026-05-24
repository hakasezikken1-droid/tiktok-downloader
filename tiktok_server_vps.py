"""TikTokダウンローダー Webサーバー（VPS版・固定IP）"""

import os
import subprocess
import requests as req
from flask import Flask, request, jsonify, send_from_directory, render_template_string

SAVE_DIR = "/var/www/tiktok"
os.makedirs(SAVE_DIR, exist_ok=True)

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TikTok Downloader</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      background: #111;
      color: #fff;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .card {
      background: #1a1a1a;
      border-radius: 16px;
      padding: 28px 24px;
      width: 100%;
      max-width: 480px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    }
    h1 { font-size: 1.4rem; margin-bottom: 6px; color: #fe2c55; }
    p.sub { font-size: 0.85rem; color: #888; margin-bottom: 20px; }
    input[type=text] {
      width: 100%;
      padding: 14px;
      border: 1px solid #333;
      border-radius: 10px;
      background: #222;
      color: #fff;
      font-size: 1rem;
      outline: none;
      margin-bottom: 12px;
    }
    input[type=text]:focus { border-color: #fe2c55; }
    button {
      width: 100%;
      padding: 14px;
      background: #fe2c55;
      color: #fff;
      border: none;
      border-radius: 10px;
      font-size: 1rem;
      font-weight: bold;
      cursor: pointer;
    }
    button:disabled { background: #555; cursor: default; }
    #status {
      margin-top: 16px;
      padding: 12px;
      border-radius: 10px;
      font-size: 0.9rem;
      display: none;
    }
    #status.info  { background: #1e3a5f; color: #7ecfff; display: block; }
    #status.ok    { background: #1a3a1a; color: #7fff7e; display: block; }
    #status.error { background: #3a1a1a; color: #ff7e7e; display: block; }
  </style>
</head>
<body>
  <div class="card">
    <h1>TikTok Downloader</h1>
    <p class="sub">TikTokのURLを貼り付けてダウンロード</p>
    <input type="text" id="url" placeholder="https://www.tiktok.com/@.../video/..." />
    <button id="btn" onclick="startDownload()">ダウンロード</button>
    <div id="status"></div>
  </div>
  <script>
    function setStatus(msg, type) {
      const el = document.getElementById('status');
      el.textContent = msg;
      el.className = type;
    }
    async function startDownload() {
      const url = document.getElementById('url').value.trim();
      if (!url) { setStatus('URLを入力してください', 'error'); return; }
      document.getElementById('btn').disabled = true;
      setStatus('ダウンロード中...', 'info');
      try {
        const res = await fetch('/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.ok) {
          const el = document.getElementById('status');
          el.className = 'ok';
          el.innerHTML = '✓ 完了 &nbsp;<a href="/dl/' + encodeURIComponent(data.filename) + '" download style="color:#fff;background:#27ae60;padding:6px 16px;border-radius:8px;text-decoration:none;font-weight:bold;">📥 保存</a>';
          document.getElementById('url').value = '';
        } else {
          setStatus('エラー: ' + data.error, 'error');
        }
      } catch (e) {
        setStatus('通信エラーが発生しました', 'error');
      }
      document.getElementById('btn').disabled = false;
    }
    document.getElementById('url').addEventListener('keydown', e => {
      if (e.key === 'Enter') startDownload();
    });
  </script>
</body>
</html>"""


YTDLP = "/opt/tiktok-venv/bin/yt-dlp"
COOKIES_FILE = "/root/cookies.txt"


def _download_file(video_url: str, filename: str) -> str:
    filepath = os.path.join(SAVE_DIR, filename)
    with req.get(video_url, stream=True, timeout=120, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    }) as r:
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    return filename


def _try_tikwm(url: str) -> str:
    resp = req.post(
        "https://www.tikwm.com/api/",
        data={"url": url, "hd": "1"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg", "tikwm API失敗"))
    item = data["data"]
    video_url = item.get("hdplay") or item.get("play")
    author = item.get("author", {}).get("unique_id", "tiktok")
    video_id = item.get("id", "unknown")
    return _download_file(video_url, f"{author}_{video_id}.mp4")


def do_download(url: str) -> str:
    cmd = [
        YTDLP,
        "--no-warnings",
        "-o", os.path.join(SAVE_DIR, "%(uploader_id)s_%(id)s.%(ext)s"),
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--print", "after_move:filepath",
    ]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode == 0:
        filepath = result.stdout.strip().splitlines()[-1]
        return os.path.basename(filepath)

    # yt-dlp失敗時はtikwm API経由でダウンロード
    return _try_tikwm(url)


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify(ok=False, error="URLが空です")
    try:
        filename = do_download(url)
        return jsonify(ok=True, filename=filename)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/dl/<path:filename>")
def serve_file(filename):
    return send_from_directory(SAVE_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
