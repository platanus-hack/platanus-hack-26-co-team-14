"""
Levanta todo de una: servidor + tunel publico, y escribe la URL en .env.

    python arrancar.py

Deja el servidor corriendo en primer plano. Ctrl+C para parar todo.
Cada vez que lo corras la URL del tunel CAMBIA: el script la reescribe sola
en .env y te la imprime para que la pegues en Kapso.
"""

from __future__ import annotations

import os
import platform
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent
HERR = RAIZ / "herramientas"
LOG_TUNEL = HERR / "tunel.log"
PUERTO = int(os.getenv("PORT", "8000"))

DESCARGAS = {
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
    ("Windows", "ARM64"): "cloudflared-windows-arm64.exe",
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
    ("Darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
    ("Darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
}

procesos: list[subprocess.Popen] = []


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def conseguir_cloudflared() -> Path:
    HERR.mkdir(exist_ok=True)
    exe = HERR / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
    if exe.exists():
        return exe

    clave = (platform.system(), platform.machine())
    archivo = DESCARGAS.get(clave)
    if not archivo:
        sys.exit(f"No hay build de cloudflared para {clave}. Instalalo a mano.")
    if archivo.endswith(".tgz"):
        sys.exit("En macOS instala cloudflared con:  brew install cloudflared")

    url = ("https://github.com/cloudflare/cloudflared/releases/latest/download/"
           + archivo)
    log(f"descargando cloudflared (~50 MB)...")
    urllib.request.urlretrieve(url, exe)
    if os.name != "nt":
        exe.chmod(0o755)
    log("cloudflared listo")
    return exe


def liberar_puerto() -> None:
    """En Windows dos uvicorn pueden escuchar el mismo puerto y responde el viejo."""
    if os.name != "nt":
        subprocess.run(["pkill", "-f", "uvicorn app:app"], capture_output=True)
        return
    salida = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids = {
        linea.split()[-1]
        for linea in salida.splitlines()
        if f":{PUERTO} " in linea and "LISTENING" in linea
    }
    for pid in pids:
        log(f"matando proceso viejo en el puerto {PUERTO} (pid {pid})")
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    if pids:
        time.sleep(2)


def arrancar_servidor() -> subprocess.Popen:
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app",
         "--host", "127.0.0.1", "--port", str(PUERTO)],
        cwd=RAIZ, env=entorno,
    )
    procesos.append(p)
    return p


def arrancar_tunel(exe: Path) -> str:
    LOG_TUNEL.unlink(missing_ok=True)
    with open(LOG_TUNEL, "w") as f:
        p = subprocess.Popen(
            [str(exe), "tunnel", "--url", f"http://127.0.0.1:{PUERTO}",
             "--no-autoupdate"],
            stdout=f, stderr=subprocess.STDOUT,
        )
    procesos.append(p)

    log("abriendo tunel...")
    patron = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    for _ in range(60):
        time.sleep(1)
        if LOG_TUNEL.exists():
            if m := patron.search(LOG_TUNEL.read_text(errors="ignore")):
                return m.group(0)
    sys.exit(f"El tunel no arranco. Mira {LOG_TUNEL}")


def escribir_env(url: str) -> None:
    env = RAIZ / ".env"
    if not env.exists():
        sys.exit("No existe .env — copialo de .env.example y rellena las llaves.")
    lineas = [l for l in env.read_text(encoding="utf-8").splitlines()
              if not l.strip().startswith("PUBLIC_BASE_URL=")]
    lineas.append(f"PUBLIC_BASE_URL={url}")
    env.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def apagar(*_) -> None:
    print("\n  cerrando...", flush=True)
    for p in procesos:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, apagar)
    signal.signal(signal.SIGTERM, apagar)

    print("\n  == ARRANCANDO TUTELA VOZ ==\n", flush=True)
    exe = conseguir_cloudflared()
    liberar_puerto()

    # 1) servidor temporal, solo para que el tunel tenga a quien apuntar
    servidor = arrancar_servidor()
    time.sleep(4)

    # 2) tunel -> URL publica
    url = arrancar_tunel(exe)
    escribir_env(url)
    log(f"URL publica: {url}")

    # 3) reiniciar el servidor para que lea la URL nueva del .env
    log("reiniciando el servidor con la URL cargada...")
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except subprocess.TimeoutExpired:
        servidor.kill()
    procesos.remove(servidor)
    liberar_puerto()
    arrancar_servidor()
    time.sleep(4)

    barra = "=" * 66
    ruta = os.getenv("WEBHOOK_PATH", "/webhooks/whatsapp")
    print("\n" + barra)
    print("  PEGA ESTO EN KAPSO  ->  Endpoint URL")
    print(barra)
    print(f"\n      {url}{ruta}\n")
    print(barra)
    print("  Ctrl+C para parar. Si cierras esto, la URL deja de servir")
    print("  y la proxima vez sera OTRA distinta.")
    print(barra + "\n", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        apagar()


if __name__ == "__main__":
    main()
