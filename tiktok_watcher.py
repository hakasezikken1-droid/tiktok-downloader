"""GitHubの変更を60秒ごとに確認してサーバーを自動再起動する"""

import subprocess
import time
import os
import sys

REPO_DIR = os.path.expanduser("~")
SERVER_SCRIPT = os.path.join(REPO_DIR, "tiktok_server.py")


def git_pull():
    result = subprocess.run(
        ["git", "pull"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()


def start_server():
    subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)
    return subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
        cwd=REPO_DIR
    )


print("✓ TikTok Downloader 監視開始（60秒ごとにGitHubを確認）")
proc = start_server()

while True:
    time.sleep(60)
    output = git_pull()
    if "Already up to date." not in output and output:
        print(f"変更を検出 → サーバーを再起動します\n{output}")
        proc.terminate()
        proc.wait()
        proc = start_server()
