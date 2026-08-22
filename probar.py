"""
Banco de pruebas de extracción.  python probar.py
Sin argumentos corre los 3 casos; con argumento prueba tu propio texto:
    python probar.py "lo que dijo la persona"
"""
import json
import sys
from extraccion import extraer, TRIAGE

CASOS = {
    "1. INSULINA (el del demo)":
        "pues yo llevo como tres semanas yendo allá por la insulina y siempre me "
        "dicen que vuelva mañana, y eso que la doctora me la mandó desde antes de "
        "Semana Santa. Ya con mis 78 años me cuesta mucho estar yendo.",

    # Trampa: menciona síntomas pero NO la EPS ni la ciudad. Si Haiku las llena,
    # el verificador debe descartarlas.
    "2. TRAMPA (sin EPS ni ciudad)":
        "me mandaron unas pastillas para la tensión y no me las han dado, ya llevo "
        "un mes esperando y me siento mal, mareada todo el tiempo.",

    # Trampa: 'ya reclamé' NO es 'gané una tutela y no cumplieron'
    "3. TRAMPA (reclamo ≠ tutela ganada)":
        "yo ya fui varias veces a reclamar y puse una queja en la EPS Sanitas pero "
        "nada, no me autorizan la cirugía de la rodilla.",
}


def mostrar(titulo, texto):
    print("=" * 70)
    print(titulo)
    print(f'  "{texto[:90]}..."' if len(texto) > 90 else f'  "{texto}"')
    print("-" * 70)

    r = extraer(texto)

    print("CRUDO (lo que devolvió Haiku):")
    for k, c in r["crudo"].items():
        if c.get("valor") is not None:
            print(f'  {k:<24} {str(c["valor"])[:28]:<30} conf={c["confianza"]:.2f}')
            print(f'  {"":24} └─ "{c.get("evidencia")}"')

    print(f'\nDESCARTADOS: {len(r["descartados"])}')
    for k, v, e in r["descartados"]:
        print(f'  ✗ {k:<22} "{v}"  <- evidencia inexistente: "{e}"')

    print("\nTRIAGE resuelto:")
    for k in TRIAGE:
        print(f'  {k:<24} {r["slots"].get(k)}')

    print(f'\n>>> RUTA: {r["ruta"].upper()}\n')


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mostrar("TU TEXTO", " ".join(sys.argv[1:]))
    else:
        for t, x in CASOS.items():
            mostrar(t, x)