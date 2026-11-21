"""One-command local start (called by start.bat / start.sh; standard library only).

Steps:
  1. install / update the project into the current virtualenv (only when pyproject.toml changed)
  2. create .env from .env.example if it does not exist
  3. create the SQLite database and load the two evaluation scenarios on first run
  4. start the API on a free port and open http://127.0.0.1:<port>/docs in the browser

Options:
  --port N        first port to try (default: $PORT or 8001; the next free one is used if taken)
  --minimal       skip the embedding model (keyword-style search only, smallest install)
  --reset         delete the local database and load the scenarios again
  --no-browser    do not open the browser
  --reload        restart the server when code changes (for development)
"""

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
STAMP = Path(sys.prefix) / ".group16-install-stamp"
SCENARIOS = "scripts/seed_workspace/scenario_*.yaml"


def say(message: str) -> None:
    print(f"[group16] {message}", flush=True)


def run(cmd: list[str], env: dict | None = None) -> bool:
    return subprocess.run(cmd, cwd=REPO, env=env).returncode == 0


def install(minimal: bool) -> None:
    extras = "" if minimal else "embeddings"
    wanted = hashlib.sha256((REPO / "pyproject.toml").read_bytes() + extras.encode()).hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == wanted:
        return
    target = f".[{extras}]" if extras else "."
    say(f"安裝套件中（{target}），第一次需要幾分鐘…")
    pip = [PY, "-m", "pip", "install", "--disable-pip-version-check", "-e"]
    if not run(pip + [target]):
        if not extras:
            sys.exit("[group16] 套件安裝失敗，請檢查網路連線後再試一次。")
        say("embedding 模型套件裝不起來（可能是這台電腦的平台不支援），改用精簡安裝：搜尋只比對字詞。")
        if not run(pip + ["."]):
            sys.exit("[group16] 套件安裝失敗，請檢查網路連線後再試一次。")
        wanted = hashlib.sha256((REPO / "pyproject.toml").read_bytes()).hexdigest()
    STAMP.write_text(wanted)


def ensure_env_file() -> None:
    env_file = REPO / ".env"
    if not env_file.exists():
        shutil.copyfile(REPO / ".env.example", env_file)
        say("已建立 .env（預設設定即可使用；要接 GitHub / Notion / Discord 再填 token）。")


def load_scenarios(env: dict, reset: bool) -> dict:
    """Returns the environment to use from now on (may switch to hashing if the model cannot be loaded)."""
    say("檢查資料庫…（第一次啟動會下載約 90 MB 的 embedding 模型）")
    cmd = [PY, "scripts/ingest.py", "--init-db", "--if-empty", "--scenario", SCENARIOS]
    if reset:
        cmd.append("--reset")
    if run(cmd, env):
        return env
    if env.get("EMBEDDING_PROVIDER") == "hashing":
        sys.exit("[group16] 匯入資料失敗，請看上面的錯誤訊息。")
    say("匯入失敗（原因見上方）。改用離線模式（不用 embedding 模型，只比對字詞）再試一次…")
    env = {**env, "EMBEDDING_PROVIDER": "hashing"}
    if not run(cmd, env):
        sys.exit("[group16] 匯入資料仍然失敗，問題不在 embedding 模型，請看上面的錯誤訊息。")
    say("已用離線模式啟動。之後有網路時重新執行，就會自動改用 embedding 模型。")
    return env


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    sys.exit(f"[group16] {start}–{start + 49} 的 port 都被佔用了，請用 --port 指定其他 port。")


def open_browser_when_ready(url: str) -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2):
                break
        except OSError:
            time.sleep(0.5)
    else:
        return
    say(f"已啟動：{url}/docs   （按 Ctrl+C 停止）")
    webbrowser.open(f"{url}/docs")


def main() -> None:
    if sys.version_info < (3, 11):  # noqa: UP036 - may be run directly by an older Python
        sys.exit("[group16] 需要 Python 3.11 以上。")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8001)))
    parser.add_argument("--minimal", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    install(args.minimal)
    ensure_env_file()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if args.minimal:
        env["EMBEDDING_PROVIDER"] = "hashing"
    env = load_scenarios(env, args.reset)

    port = free_port(args.port)
    if port != args.port:
        say(f"port {args.port} 被佔用，改用 {port}。")
    url = f"http://127.0.0.1:{port}"
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    else:
        say(f"啟動中：{url}/docs   （按 Ctrl+C 停止）")

    cmd = [PY, "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(port)]
    if args.reload:
        cmd.append("--reload")
    server = subprocess.Popen(cmd, cwd=REPO, env=env)
    try:
        sys.exit(server.wait())
    except KeyboardInterrupt:
        server.terminate()
        server.wait()
        say("已停止。")


if __name__ == "__main__":
    main()
