"""TikTokダウンローダー Webサーバー（VPS版・固定IP）"""

import os
import re
import json
from http.cookiejar import MozillaCookieJar
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
          setStatus('✓ 完了: ' + data.filename, 'ok');
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


def make_session() -> req.Session:
    session = req.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        "Referer": "https://www.tiktok.com/",
    })
    cookies_file = "/root/cookies.txt"
    if os.path.exists(cookies_file):
        jar = MozillaCookieJar()
        jar.load(cookies_file, ignore_discard=True, ignore_expires=True)
        session.cookies = jar
    return session


def do_download(url: str) -> str:
    session = make_session()

    resp = session.get(url, allow_redirects=True, timeout=30)
    full_url = resp.url

    match = re.search(r"/video/(\d+)", full_url)
    if not match:
        raise RuntimeError(f"動画IDが取得できませんでした: {full_url}")
    video_id = match.group(1)
    author_id = "tiktok"
    download_url = None

    html = resp.text
    m = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if m:
        try:
            data = json.loads(m.group(1))
            item = (
                data
                .get("__DEFAULT_SCOPE__", {})
                .get("webapp.video-detail", {})
                .get("itemInfo", {})
                .get("itemStruct", {})
            )
            video = item.get("video", {})
            author_id = item.get("author", {}).get("uniqueId", "tiktok")
            download_url = video.get("playAddr") or video.get("downloadAddr")
        except Exception:
            pass

    if not download_url:
        api = session.get(
            f"https://www.tiktok.com/api/item/detail/?itemId={video_id}&webapp_id=1988",
            timeout=30,
        )
        if api.ok:
            try:
                item = api.json().get("itemInfo", {}).get("itemStruct", {})
                video = item.get("video", {})
                author_id = item.get("author", {}).get("uniqueId", "tiktok")
                download_url = video.get("playAddr") or video.get("downloadAddr")
            except Exception:
                pass

    if not download_url:
        raise RuntimeError("動画URLが取得できませんでした。cookies.txtが必要な可能性があります。")

    filename = f"{author_id}_{video_id}.mp4"
    filepath = os.path.join(SAVE_DIR, filename)

    with session.get(download_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

    return filename


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
    app.run(host="0.0.0.0", port=5000, debug=False)
