import io, os, socket, json, subprocess, tempfile, time

VNC_HOST = os.environ.get("VNC_HOST", "127.0.0.1")
VNC_PORT = os.environ.get("VNC_PORT", "5900")
VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "")
QMP_SOCK = os.environ.get("QMP_SOCK", "/tmp/vm-qmp.sock")

_vncdo = os.environ.get("VNCDO_PATH") or os.path.expanduser("~/projects/charlyndesktop/.venv/bin/vncdo")

_QKEY_MAP = {
    ' ': 'spc', '-': 'minus', '.': 'dot', '/': 'slash', '=': 'equal',
    ',': 'comma', ';': 'semicolon', "'": 'apostrophe', '[': 'bracket_left',
    ']': 'bracket_right', '\\': 'backslash', '`': 'grave_accent',
    'enter': 'ret', 'tab': 'tab', 'escape': 'esc', 'backspace': 'backspace',
    'delete': 'delete', 'up': 'up', 'down': 'down', 'left': 'left',
    'right': 'right', 'home': 'home', 'end': 'end', 'pageup': 'pgup',
    'pagedown': 'pgdn', 'super': 'super_l', 'ctrl': 'ctrl_l', 'alt': 'alt_l',
    'shift': 'shift_l', 'capslock': 'caps_lock',
}

def _qmp(cmd):
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(5)
    s.connect(QMP_SOCK)
    s.recv(4096)
    s.send(json.dumps({'execute': 'qmp_capabilities'}).encode() + b'\n')
    time.sleep(0.05)
    s.recv(4096)
    s.send(json.dumps(cmd).encode() + b'\n')
    time.sleep(0.2)
    data = s.recv(8192)
    s.close()
    return data

def _qmp_key(key_name):
    _qmp({'execute': 'send-key', 'arguments': {
        'keys': [{'type': 'qcode', 'data': key_name}]
    }})

def _vnc(*cmds):
    args = [_vncdo, "-s", f"{VNC_HOST}::{VNC_PORT}"]
    if VNC_PASSWORD:
        args += ["-p", VNC_PASSWORD]
    args += list(cmds)
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"vncdo error: {r.stderr.strip() or r.stdout.strip()}")
    return r

_BTN_MAP = {1: 'left', 2: 'middle', 3: 'right'}

def _qmp_click(x, y, button=1):
    _vnc("move", str(x), str(y))
    time.sleep(0.1)
    btn = _BTN_MAP.get(button, 'left')
    _qmp({'execute': 'input-send-event', 'arguments': {
        'events': [
            {'type': 'btn', 'data': {'button': btn, 'down': True}},
            {'type': 'btn', 'data': {'button': btn, 'down': False}},
        ]
    }})

def click(x, y, button=1):
    _qmp_click(x, y, button)

def double_click(x, y):
    click(x, y)
    time.sleep(0.1)
    click(x, y)

def right_click(x, y):
    click(x, y, button=3)

def move(x, y):
    _vnc("move", str(x), str(y))

_SHIFTED = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
    '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\',
    ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
}

def _qmp_chord(*keys):
    events = []
    for k in keys:
        events.append({'type': 'key', 'data': {'key': {'type': 'qcode', 'data': k}, 'down': True}})
    for k in reversed(keys):
        events.append({'type': 'key', 'data': {'key': {'type': 'qcode', 'data': k}, 'down': False}})
    _qmp({'execute': 'input-send-event', 'arguments': {'events': events}})

def type_text(text):
    for ch in text:
        if ch.isupper():
            _qmp_chord('shift', ch.lower())
        elif ch in _SHIFTED:
            _qmp_chord('shift', _SHIFTED[ch])
        elif ch.isalpha():
            _qmp_key(ch.lower())
        elif ch.isdigit():
            _qmp_key(ch)
        elif ch in _QKEY_MAP:
            _qmp_key(_QKEY_MAP[ch])
        else:
            _qmp_key(ch)
        time.sleep(0.01)

def key_press(key):
    key = key.lower()
    if '-' in key:
        parts = [_QKEY_MAP.get(p, p) for p in key.split('-')]
        events = []
        for p in parts:
            events.append({'type': 'key', 'data': {'key': {'type': 'qcode', 'data': p}, 'down': True}})
        for p in reversed(parts):
            events.append({'type': 'key', 'data': {'key': {'type': 'qcode', 'data': p}, 'down': False}})
        _qmp({'execute': 'input-send-event', 'arguments': {'events': events}})
    else:
        mapped = _QKEY_MAP.get(key, key)
        _qmp_key(mapped)

def screenshot():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        _vnc("capture", path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)

def screenshot_to_file(path):
    _vnc("capture", path)

def screen_size():
    from PIL import Image
    data = screenshot()
    return Image.open(io.BytesIO(data)).size
