# Tutela Voz

Tutela Voz es un asistente conversacional por voz que ayuda a personas a
ejercer sus derechos en salud en Colombia, guiándolas para radicar una
**acción de tutela**, un **desacato** o una **PQRD**, sin necesidad de saber
redactar un documento legal.

## Problema

Muchas personas no logran ejercer su derecho a la salud porque no saben
cómo redactar una tutela, desconocen los plazos del desacato, o no
distinguen cuándo basta con una PQRD. El lenguaje jurídico y los formularios
son una barrera real.

## Solución

El usuario simplemente habla (por WhatsApp, vía Kapso). El sistema:

1. Transcribe el audio.
2. Extrae la información necesaria (cédula, EPS, municipio, hechos, fechas).
3. Aplica un triage **determinístico** para decidir la ruta (tutela,
   desacato o PQRD) — nunca una decisión probabilística del modelo.
4. Genera el documento final combinando plantillas, citas jurídicas
   verificadas (`citas.json`) y el listado del Plan de Beneficios en Salud
   (`pbs.json`).
5. Entrega un PDF listo para radicar, junto con un resumen en texto.

## Principio de diseño

> El modelo de lenguaje interviene solo en la **entrada** (transcripción y
> extracción de datos estructurados). Nunca decide la ruta jurídica, nunca
> selecciona jurisprudencia y nunca genera contenido jurídico libremente.
> Todo lo jurídico se resuelve con reglas determinísticas y fuentes
> verificadas.

## Estado actual

- Canal de entrada (webhook de Kapso, transcripción): en desarrollo.
- Núcleo de triage y slots: implementado y probado.
- Extracción de texto a slots: en desarrollo.
- Generación de documentos jurídicos: en desarrollo.
