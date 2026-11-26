"""tui.py — the full-screen terminal front door for search-media.

Flow (all in one Textual app, filling the whole terminal):

    1. Configure   — arrow-key config editor (dim, image tokens, video fps,
                      query prefix, media folder, top results)
    2. Brain        — starts llama-server (detached) and shows a +++ bar
    3. Indexing     — runs the indexer with a live +++ bar + file stats
    4. Web + Done   — starts the web app (detached), opens the browser

The server and web app are started as detached background processes
(start_new_session) so they keep running after the TUI exits — that's the
"deploy" behavior. `python tui.py stop` shuts them down.

Run:  ./run.sh            (interactive deploy)
      ./run.sh stop        (stop server + web app)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser

import requests
from textual import App, work
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from build_index import run_indexing
from common import EmbeddingClient, load_config, save_config, server_url

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

# (key, label, options-or-None). None => free-text (typed).
CONFIG_ITEMS = [
    ("dim", "Vector dimension", [768, 512, 256]),
    ("image_tokens", "Image tokens", [280, 560, 1120]),
    ("video_fps", "Video FPS", [1, 2, 4]),
    ("query_prefix", "Query prefix", [True, False]),
    ("media_folder", "Media folder", None),
    ("top_n", "Top results", [5, 10, 20, 50]),
]


# --------------------------------------------------------------------------- #
# Shared state (written by the worker thread, read by the UI interval)
# --------------------------------------------------------------------------- #


class State:
    def __init__(self):
        self.stage = "server"
        self.frac = 0.0
        self.status = "starting…"
        self.done = 0
        self.total = 0
        self.skipped = 0
        self.failed = 0
        self.current = ""
        self.started = time.time()
        self.finished = False
        self.error = ""


# --------------------------------------------------------------------------- #
# The +++ bar
# --------------------------------------------------------------------------- #


class PlusBar(Static):
    def __init__(self, width: int = 64, **kwargs):
        super().__init__(**kwargs)
        self.width = width
        self.set(0.0)

    def set(self, frac: float):
        frac = max(0.0, min(1.0, frac))
        filled = int(frac * self.width)
        self.update("+" * filled + "-" * (self.width - filled))


# --------------------------------------------------------------------------- #
# Config screen
# --------------------------------------------------------------------------- #


def _fmt(key, value):
    if key == "query_prefix":
        return "ON" if value else "OFF"
    return str(value)


class ConfigScreen(Screen):
    BINDINGS = [Binding("escape", "quit", "Quit")]

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.values = {
            "dim": cfg["embedding"]["dim"],
            "image_tokens": cfg["server"]["image_tokens"],
            "video_fps": cfg["server"]["video_fps"],
            "query_prefix": cfg["embedding"]["query_prefix"],
            "media_folder": cfg["media_folder"],
            "top_n": cfg["web"]["top_n"],
        }
        self.selected = 0

    def compose(self):
        yield Static("SEARCH MEDIA · EmbeddingGemma-2 · local index", id="title")
        yield Static("↑↓ select   ←→ change   Enter start   Esc quit", id="hint")
        for key, label, options in CONFIG_ITEMS:
            yield Static("", id=f"row-{key}")
        yield Static("▶  Start indexing & launch", id="cta")

    def on_mount(self):
        self.refresh_rows()

    def refresh_rows(self):
        for key, label, options in CONFIG_ITEMS:
            row = self.query_one(f"#row-{key}", Static)
            idx = CONFIG_ITEMS.index((key, label, options))
            sel = "  " if idx == self.selected else "→ "
            value = _fmt(key, self.values[key])
            opts = f"  [{ ' · '.join(str(o) for o in options) }]" if options else ""
            row.update(f"{sel}{label:<16} {value}{opts}")
            row.styles.background = "rgb(30, 60, 120)" if idx == self.selected else "transparent"

    def cycle(self, i: int, direction: int):
        key, _label, options = CONFIG_ITEMS[i]
        if options is None:
            return
        cur = self.values[key]
        try:
            pos = options.index(cur)
        except ValueError:
            self.values[key] = options[0]
            return
        self.values[key] = options[(pos + direction) % len(options)]

    def on_key(self, event):
        key = event.key
        if key in ("up", "down"):
            self.selected = (self.selected + (1 if key == "down" else -1)) % len(CONFIG_ITEMS)
            self.refresh_rows()
            return
        if key in ("left", "right"):
            self.cycle(self.selected, -1 if key == "left" else 1)
            self.refresh_rows()
            return
        if key == "enter":
            self.start()
            return
        if key == "backspace":
            cur_key, _, options = CONFIG_ITEMS[self.selected]
            if options is None:
                self.values[cur_key] = self.values[cur_key][:-1]
                self.refresh_rows()
            return
        # free-text typing
        cur_key, _, options = CONFIG_ITEMS[self.selected]
        if options is None and event.character:
            self.values[cur_key] += event.character
            self.refresh_rows()

    def start(self):
        # write the chosen values back into the config
        self.cfg["embedding"]["dim"] = self.values["dim"]
        self.cfg["server"]["image_tokens"] = self.values["image_tokens"]
        self.cfg["server"]["video_fps"] = self.values["video_fps"]
        self.cfg["embedding"]["query_prefix"] = self.values["query_prefix"]
        self.cfg["media_folder"] = self.values["media_folder"]
        self.cfg["web"]["top_n"] = self.values["top_n"]
        save_config(CONFIG_PATH, self.cfg)
        self.app.push_screen(ProgressScreen(self.cfg))


# --------------------------------------------------------------------------- #
# Progress screen (server -> index -> web -> done)
# --------------------------------------------------------------------------- #


class ProgressScreen(Screen):
    BINDINGS = [Binding("escape", "quit", "Quit")]

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.state = State()

    def compose(self):
        yield Static("DEPLOY", id="title")
        yield Static("", id="stage")
        yield PlusBar(width=64, id="bar")
        yield Static("", id="status")
        yield Static("", id="stats")
        yield Static("Esc to leave (server & web app keep running)", id="hint")

    def on_mount(self):
        self.set_interval(0.2, self.refresh)
        self.run_worker(self.workflow, exclusive=True)

    def refresh(self):
        s = self.state
        self.query_one("#stage", Static).update(self._stage_label())
        self.query_one("#bar", PlusBar).set(s.frac)
        self.query_one("#status", Static).update(s.status)
        if s.stage == "index" and s.total:
            rate = s.done / (time.time() - s.started) if s.started and time.time() > s.started else 0
            self.query_one("#stats", Static).update(
                f"{s.done + s.skipped}/{s.total} files · skip {s.skipped} · "
                f"fail {s.failed} · {rate:.1f}/s · {s.current[:40]}"
            )
        elif s.stage == "done":
            url = f"http://{self.cfg['web']['host']}:{self.cfg['web']['port']}"
            self.query_one("#stats", Static).update(f"web app → {url}")
        else:
            self.query_one("#stats", Static).update("")

    def _stage_label(self):
        s = self.state
        return {
            "server": "Starting brain (llama-server)",
            "index": f"Indexing  {self.cfg['media_folder']}",
            "web": "Starting web app",
            "done": "✓ Ready",
        }.get(s.stage, s.stage)

    @work(exclusive=True)
    def workflow(self):
        s = self.state
        try:
            self._start_server(s)
            self._run_index(s)
            self._start_web(s)
            self._open_browser(s)
        except Exception as e:
            s.error = f"{type(e).__name__}: {e}"
            s.status = f"ERROR: {s.error}"
            s.finished = True
        finally:
            s.stage = "done"
            s.frac = 1.0
            s.finished = True

    # -- stages ----------------------------------------------------------- #

    def _start_server(self, s: State):
        s.stage = "server"
        s.status = "checking server…"
        if _server_healthy(self.cfg):
            s.status = "brain already running"
            s.frac = 1.0
            return
        s.status = "starting llama-server (loading 768-d model + vision)…"
        _start_server(self.cfg)
        for _ in range(120):  # up to ~90s
            s.frac = min(s.frac + 0.015, 0.95)
            time.sleep(0.5)
            if _server_healthy(self.cfg):
                break
        s.frac = 1.0
        s.status = "brain ready"
        time.sleep(0.6)

    def _run_index(self, s: State):
        s.stage = "index"
        s.started = time.time()

        def cb(done, total, skipped, failed, current, kind, started):
            s.done = done
            s.total = total
            s.skipped = skipped
            s.failed = failed
            s.current = current
            s.frac = (done + skipped) / total if total else 0.0

        summary = run_indexing(self.cfg, on_progress=cb)
        s.status = (f"indexed {summary['encoded']} · skipped {summary['skipped']} · "
                    f"failed {summary['failed']} in {summary['seconds']:.0f}s")
        s.frac = 1.0
        time.sleep(0.8)

    def _start_web(self, s: State):
        s.stage = "web"
        s.status = "checking web app…"
        if _web_healthy(self.cfg):
            s.status = "web app already running"
            s.frac = 1.0
            return
        s.status = "starting Flask web app…"
        _start_web(self.cfg)
        for _ in range(40):
            time.sleep(0.5)
            if _web_healthy(self.cfg):
                break
        s.frac = 1.0
        s.status = "web app ready"
        time.sleep(0.6)

    def _open_browser(self, s: State):
        s.stage = "done"
        s.status = "opening browser…"
        url = f"http://{self.cfg['web']['host']}:{self.cfg['web']['port']}"
        try:
            webbrowser.open(url)
        except Exception:
            pass
        s.frac = 1.0


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #


class SearchMediaApp(App):
    CSS = """
    #title { text-style: bold; color: #4f8cff; padding: 1 0; }
    #hint  { color: #8a93a3; padding: 0 0 1 0; }
    #cta   { color: #37d0a0; text-style: bold; padding: 1 0; }
    #bar   { color: #4f8cff; text-style: bold; padding: 1 0; }
    #status{ color: #e6e9ef; padding: 0 0 1 0; }
    #stats { color: #8a93a3; }
    """

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg

    def on_mount(self):
        self.push_screen(ConfigScreen(self.cfg))


# --------------------------------------------------------------------------- #
# Subprocess helpers (detached so they outlive the TUI)
# --------------------------------------------------------------------------- #


def _server_healthy(cfg) -> bool:
    emb = cfg["embedding"]
    return EmbeddingClient(
        base_url=server_url(cfg), dim=emb["dim"],
        query_prefix=emb["query_prefix"], query_prefix_text=emb["query_prefix_text"],
    ).healthy()


def _web_healthy(cfg) -> bool:
    try:
        r = requests.get(
            f"http://{cfg['web']['host']}:{cfg['web']['port']}/health", timeout=3
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def _start_server(cfg):
    s = cfg["server"]
    cmd = [
        s["binary"],
        "--model", s["model"],
        "--mmproj", s["mmproj"],
        "--embedding",
        "--pooling", s["pooling"],
        "--embd-normalize", str(s["normalize"]),
        "--host", s["host"],
        "--port", str(s["port"]),
        "-c", str(s["ctx_size"]),
        "-ub", str(s["ubatch"]),
        "--image-max-tokens", str(s["image_tokens"]),
        "--video-fps", str(s["video_fps"]),
    ]
    log = open(os.path.join(HERE, ".server.log"), "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True, cwd=HERE)
    with open(os.path.join(HERE, ".server.pid"), "w") as f:
        f.write(str(proc.pid))


def _start_web(cfg):
    log = open(os.path.join(HERE, ".web.log"), "w")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "app.py")],
        stdout=log, stderr=log, start_new_session=True, cwd=HERE,
    )
    with open(os.path.join(HERE, ".web.pid"), "w") as f:
        f.write(str(proc.pid))


# --------------------------------------------------------------------------- #
# stop mode
# --------------------------------------------------------------------------- #


def stop():
    for name in ("server", "web"):
        pidfile = os.path.join(HERE, f".{name}.pid")
        if os.path.exists(pidfile):
            try:
                pid = int(open(pidfile).read().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"stopped {name} (pid {pid})")
            except (ValueError, ProcessLookupError) as e:
                print(f"could not stop {name}: {e}")
            finally:
                os.remove(pidfile)
        else:
            print(f"{name}: no pid file (not running?)")


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop()
        return
    cfg = load_config(CONFIG_PATH)
    app = SearchMediaApp(cfg)
    app.run()


if __name__ == "__main__":
    main()
