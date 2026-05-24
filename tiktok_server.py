"""TikTokダウンローダー Webサーバー（スマホ・外出先対応）"""

import os
import re
import json
import time
from http.cookiejar import MozillaCookieJar
import requests as req
from flask import Flask, request, jsonify, send_from_directory, render_template_string

SAVE_DIR = os.path.join(os.path.expanduser("~"), "Videos", "TikTok")
COOKIES_FILE = os.path.join(os.path.expanduser("~"), "cookies.txt")
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
    #filelist { margin-top: 20px; }
    #filelist h2 { font-size: 1rem; color: #aaa; margin-bottom: 10px; }
    .file-item {
      background: #222;
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
    }
    .file-item span { word-break: break-all; flex: 1; margin-right: 10px; color: #ccc; }
    .file-item a { color: #fe2c55; text-decoration: none; white-space: nowrap; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>TikTok Downloader</h1>
    <p class="sub">TikTokのURLを貼り付けてダウンロード</p>
    <input type="text" id="url" placeholder="https://www.tiktok.com/@.../video/..." />
    <button id="btn" onclick="startDownload()">ダウンロード</button>
    <div id="status"></div>
    <div id="filelist"></div>
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
          loadFiles();
        } else {
          setStatus('エラー: ' + data.error, 'error');
        }
      } catch (e) {
        setStatus('通信エラーが発生しました', 'error');
      }
      document.getElementById('btn').disabled = false;
    }
    async function loadFiles() {
      const res = await fetch('/files');
      const data = await res.json();
      const el = document.getElementById('filelist');
      if (!data.files.length) { el.innerHTML = ''; return; }
      el.innerHTML = '<h2>保存済み動画</h2>' + data.files.map(f =>
        `<div class="file-item">
          <span>${f}</span>
          <a href="/dl/${encodeURIComponent(f)}" download>保存</a>
        </div>`
      ).join('');
    }
    document.getElementById('url').addEventListener('keydown', e => {
      if (e.key === 'Enter') startDownload();
    });
    loadFiles();
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
    if os.path.exists(COOKIES_FILE):
        jar = MozillaCookieJar()
        jar.load(COOKIES_FILE, ignore_discard=True, ignore_expires=True)
        session.cookies = jar
    return session


def do_download(url: str) -> str:
    session = make_session()

    # short URLを展開して動画IDを取得
    resp = session.get(url, allow_redirects=True, timeout=30)
    full_url = resp.url

    match = re.search(r"/video/(\d+)", full_url)
    if not match:
        raise RuntimeError(f"動画IDが取得できませんでした: {full_url}")
    video_id = match.group(1)
    author_id = "tiktok"
    download_url = None

    # ページHTMLから動画URLを抽出
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

    # ページから取れなかった場合はTikTok内部APIを試みる
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
        raise RuntimeError("動画URLが取得できませんでした。TikTokへのログインが必要な可能性があります。")

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


@app.route("/files")
def list_files():
    files = sorted(
        [f for f in os.listdir(SAVE_DIR) if f.endswith((".mp4", ".webm", ".mkv"))],
        key=lambda f: os.path.getmtime(os.path.join(SAVE_DIR, f)),
        reverse=True,
    )
    return jsonify(files=files[:20])


@app.route("/dl/<path:filename>")
def serve_file(filename):
    return send_from_directory(SAVE_DIR, filename, as_attachment=True)


def notify_discord(webhook_url: str, message: str) -> None:
    try:
        req.post(webhook_url, json={"content": message}, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    import socket

    webhook_file = os.path.join(os.path.expanduser("~"), ".discord_webhook_tiktok")
    webhook_url = ""
    if os.path.exists(webhook_file):
        with open(webhook_file, encoding="utf-8-sig") as f:
            webhook_url = f.read().strip()

    from pyngrok import ngrok, conf

    token_file = os.path.join(os.path.expanduser("~"), ".ngrok_token")
    if os.path.exists(token_file):
        with open(token_file, encoding="utf-8-sig") as f:
            conf.get_default().auth_token = f.read().strip()

    tunnel = ngrok.connect(5000, "http")
    public_url = tunnel.public_url

    print(f"\n✓ TikTok Downloader 起動中")
    print(f"  外出先URL: {public_url}\n")

    if webhook_url:
        notify_discord(
            webhook_url,
            f"📱 **TikTok Downloader** 起動しました\n🔗 {public_url}"
        )
        print("  Discord に URL を通知しました\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
