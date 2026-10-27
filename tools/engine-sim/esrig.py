"""Drives engine-sim (community build v0.1.14a) through window messages and records it via WASAPI loopback.

The community build is an SDL app, so posted key and wheel messages reach it whether or not its window
is in front: nothing is ever sent to other windows. rec.exe (rec.cs) records what the default playback
device plays, so other sounds must be off while recording."""
import ctypes, ctypes.wintypes as wt, os, subprocess, time, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ES = os.environ.get('ENGINE_SIM_DIR') or os.path.join(HERE, 'engine-sim-v0.1.14a')
REC = os.path.join(HERE, 'rec.exe')
user32 = ctypes.windll.user32
WM_KEYDOWN, WM_KEYUP, WM_MOUSEWHEEL, WM_ACTIVATE, WM_SETFOCUS = 0x0100, 0x0101, 0x020A, 0x0006, 0x0007
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.MapVirtualKeyW.restype = wt.UINT


class PostedSim:
    """One engine-sim window with the given engine script (path relative to its assets folder)."""

    def __init__(self, engine_import):
        # The community build opens the engine named in bin/session_info.tmp (the last one loaded).
        with open(os.path.join(ES, 'bin', 'session_info.tmp'), 'w', newline='') as f:
            f.write('..\\assets\\' + engine_import.replace('/', '\\'))
        self.proc = subprocess.Popen([os.path.join(ES, 'bin', 'engine-sim-app.exe')], cwd=os.path.join(ES, 'bin'))
        self.hwnd = None
        for _ in range(200):
            time.sleep(0.1)
            self.hwnd = self._find()
            if self.hwnd: break
        if not self.hwnd: raise RuntimeError('engine-sim window not found')

    def _find(self):
        found = []
        def cb(h, _):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == self.proc.pid and user32.IsWindowVisible(h): found.append(h)
            return True
        user32.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(cb), 0)
        return found[0] if found else None

    def key(self, vk, down):
        # SDL drops keys while its window lacks keyboard focus, and Windows gives real focus only to the
        # first window it opens. Telling the window it has focus (it does not take it) keeps keys flowing.
        user32.PostMessageW(self.hwnd, WM_ACTIVATE, 1, 0)
        user32.PostMessageW(self.hwnd, WM_SETFOCUS, 0, 0)
        scan = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(self.hwnd, WM_KEYDOWN if down else WM_KEYUP, vk, 1 | (scan << 16) | (0 if down else 0xC0000000))

    # engine-sim reads key edges and wheel steps once per frame, and a heavy engine slows its frames, so
    # taps are held and wheel steps (100 rpm of dyno each) spaced well beyond a frame.
    TAP, STEP = 0.25, 0.2

    def tap(self, ch, hold=None):
        vk = ord(ch.upper()) if isinstance(ch, str) else ch
        self.key(vk, True); time.sleep(hold or self.TAP); self.key(vk, False); time.sleep(self.TAP)

    def wheel(self, notches, while_key=None):
        if while_key: self.key(ord(while_key), True); time.sleep(self.TAP)
        r = wt.RECT(); user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        pos = ((r.top + r.bottom) // 2 & 0xFFFF) << 16 | ((r.left + r.right) // 2 & 0xFFFF)
        step = 120 if notches > 0 else -120
        for _ in range(abs(notches)):
            user32.PostMessageW(self.hwnd, WM_MOUSEWHEEL, (step & 0xFFFF) << 16, pos)
            time.sleep(self.STEP)
        if while_key: time.sleep(self.TAP); self.key(ord(while_key), False); time.sleep(self.TAP)

    def close(self):
        self.proc.kill(); self.proc.wait()


def record(path, seconds):
    out = subprocess.run([REC, path, str(seconds)], capture_output=True, text=True)
    if out.returncode: raise RuntimeError(out.stderr)
    return path


def rms(path):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
