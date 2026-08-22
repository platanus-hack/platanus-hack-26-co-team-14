"""
Prueba el puente sin WhatsApp.

    python -m puente.probar                      llaves + TTS + STT (ida y vuelta)
    python -m puente.probar --voces              lista las voces y sus IDs
    python -m puente.probar --texto "hola"       frase a sintetizar
    python -m puente.probar --archivo demo.ogg   transcribe un audio real
    python -m puente.probar --backend            comprueba que el backend responde
    python -m puente.probar --whatsapp 573001112233   manda un mensaje de verdad

El ciclo TTS→STT es la prueba clave: genera audio con ElevenLabs y lo vuelve a
transcribir. Si el texto vuelve parecido, las dos mitades sirven.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import backend, config, kapso, voz

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OK, MAL, AVISO = "  [ok]", "  [XX]", "  [!!]"


def titulo(t: str) -> None:
    print(f"\n{t}\n" + "-" * 62)


def listar_voces() -> int:
    if not config.ELEVENLABS_API_KEY:
        print(f"{MAL} falta ELEVENLABS_API_KEY en .env")
        return 1
    try:
        voces = voz.listar_voces()
    except Exception as e:
        print(f"{MAL} {e}")
        print(f"{AVISO} si dice invalid_api_key, regenera la llave en "
              "elevenlabs.io -> Profile -> API Keys")
        return 1

    titulo(f"Voces disponibles ({len(voces)})")
    print(f"  {'VOICE ID':<24} {'NOMBRE':<20} ETIQUETAS")
    for v in voces:
        e = v["etiquetas"]
        resumen = ", ".join(str(e[k]) for k in ("language", "accent", "gender", "age")
                            if e.get(k))
        print(f"  {v['voice_id'] or '':<24} {(v['nombre'] or '')[:20]:<20} {resumen}")
    print("\n  Copia uno y ponlo en .env:  ELEVENLABS_VOICE_ID=<el que elijas>")
    return 0


def revisar_llaves() -> bool:
    titulo("1. Variables de entorno")
    faltan = config.faltantes()
    for k in ("KAPSO_API_KEY", "KAPSO_PHONE_NUMBER_ID",
              "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        v = getattr(config, k)
        print(f"{OK} {k} = {v[:8]}..." if v else f"{MAL} {k} vacia")
    print(f"{OK} BACKEND_URL = {config.BACKEND_URL}" if config.BACKEND_URL
          else f"{AVISO} BACKEND_URL vacia -> el puente responde en eco")
    print(f"{OK} modo de proceso = {config.MODO_PROCESO}")
    return not faltan


def probar_backend() -> None:
    titulo("Backend")
    if not backend.hay_backend():
        print(f"{AVISO} BACKEND_URL vacia; no hay nada que probar")
        return
    ejemplo = {
        "telefono": "573001112233",
        "mensaje_id": "prueba",
        "tipo": "audio",
        "texto": "Buenos dias, la EPS no me ha entregado la insulina",
        "transcripcion": {"texto": "Buenos dias, la EPS no me ha entregado la insulina",
                          "duracion": 4.2, "confianza": 0.93, "idioma": "spa",
                          "baja_confianza": False, "texto_kapso": None},
        "timestamp": "1730093100",
    }
    acciones = backend.procesar(ejemplo)
    print(f"{OK} devolvio {len(acciones)} accion(es):")
    for a in acciones:
        print(f"       - {a.get('tipo')}: {str(a.get('texto') or a.get('url'))[:70]}")


def probar_tts(texto: str):
    titulo("2. ElevenLabs TTS")
    try:
        audio, tipo, ext = voz.sintetizar(texto)
    except Exception as e:
        print(f"{MAL} {e}")
        return None
    salida = Path(f"prueba_tts.{ext}")
    salida.write_bytes(audio)
    print(f"{OK} {len(audio)} bytes - {tipo} - guardado en {salida}")
    print(f"{OK} OGG/Opus: se envia como nota de voz" if ext == "ogg"
          else f"{AVISO} mp3: se envia como audio normal, sin la onda de voz")
    return audio, tipo, ext


def probar_stt(audio: bytes, tipo: str, ext: str, esperado: str = "") -> None:
    titulo("3. ElevenLabs STT (Scribe)")
    try:
        tr = voz.transcribir(audio, nombre=f"prueba.{ext}", content_type=tipo)
    except Exception as e:
        print(f"{MAL} {e}")
        return
    print(f"{OK} texto     : {tr['texto']}")
    print(f"{OK} confianza : {tr['confianza']:.0%}")
    print(f"{OK} duracion  : {tr['duracion']:.1f}s")
    print(f"{OK} idioma    : {tr['idioma']}")
    if esperado:
        print(f"       esperado  : {esperado}")
    if tr["confianza"] < config.UMBRAL_CONFIANZA_STT:
        print(f"{AVISO} por debajo de UMBRAL_CONFIANZA_STT="
              f"{config.UMBRAL_CONFIANZA_STT}")


def probar_whatsapp(telefono: str) -> None:
    titulo("4. Kapso - envio real")
    try:
        kapso.enviar_texto(telefono, "Prueba del puente Tutela Voz.")
        print(f"{OK} texto enviado a {telefono}")
    except Exception as e:
        print(f"{MAL} {e}")
        print(f"{AVISO} si dice 'Active sandbox session required', escribele tu "
              "primero al numero del sandbox desde tu WhatsApp")


def main() -> int:
    p = argparse.ArgumentParser(description="Prueba el puente")
    p.add_argument("--texto", default="Buenos dias. Le repito lo que entendi "
                                      "para que usted me diga si esta bien.")
    p.add_argument("--archivo", help="transcribe este audio en vez de generar uno")
    p.add_argument("--whatsapp", help="numero destino, ej. 573001112233")
    p.add_argument("--voces", action="store_true", help="lista las voces")
    p.add_argument("--backend", action="store_true", help="prueba solo el backend")
    a = p.parse_args()

    if a.voces:
        return listar_voces()

    print("\n=== PUENTE TUTELA VOZ - PRUEBA ===")
    completo = revisar_llaves()

    if a.backend:
        probar_backend()
        return 0

    if a.archivo:
        ruta = Path(a.archivo)
        if not ruta.exists():
            print(f"\n{MAL} no existe {ruta}")
            return 1
        ext = ruta.suffix.lstrip(".") or "ogg"
        tipo = "audio/ogg" if ext in ("ogg", "opus") else "audio/mpeg"
        print(f"\n{OK} usando {ruta} ({ruta.stat().st_size} bytes)")
        probar_stt(ruta.read_bytes(), tipo, ext)
    elif config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
        if r := probar_tts(a.texto):
            probar_stt(*r, esperado=a.texto)
    else:
        print(f"\n{AVISO} sin llaves de ElevenLabs no se prueba la voz")

    probar_backend()

    if a.whatsapp:
        probar_whatsapp(a.whatsapp)

    titulo("Resumen")
    if completo:
        print(f"{OK} Llaves completas.")
    else:
        print(f"{MAL} Faltan: {', '.join(config.faltantes())}")

    if url := config.url_webhook():
        print(f"{OK} Pega esto en Kapso -> Endpoint URL:\n\n      {url}\n")
    else:
        print(f"{AVISO} Sin URL publica todavia. En local:  python arrancar.py")
    return 0 if completo else 1


if __name__ == "__main__":
    sys.exit(main())
