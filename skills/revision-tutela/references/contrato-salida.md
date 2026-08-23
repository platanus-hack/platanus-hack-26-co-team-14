# Contrato de salida

Devuelve únicamente un objeto con esta estructura lógica. Si el canal exige texto, conserva exactamente estos encabezados y orden.

```json
{
  "decision": "aprobar | corregir | bloquear",
  "tipo_documento": "tutela | derecho_peticion",
  "resumen_judicial": "máximo 120 palabras",
  "bloqueos": [
    {
      "regla": "identificador",
      "hallazgo": "problema concreto",
      "dato_faltante": "dato o prueba, o null",
      "pregunta_usuario": "una pregunta breve, o null"
    }
  ],
  "correcciones": [
    {
      "seccion": "nombre",
      "problema": "descripción",
      "correccion": "texto propuesto",
      "motivo": "razón verificable"
    }
  ],
  "checklist": [
    {
      "regla": "1",
      "resultado": "si | no | no_aplica",
      "evidencia": "ubicación o explicación breve"
    }
  ],
  "documento_corregido": "texto completo o null",
  "mensaje_para_usuario": "explicación clara, sin jerga ni promesas"
}
```

## Condiciones

- Incluye las 43 reglas en `checklist`.
- Si `decision` es `bloquear`, `documento_corregido` debe ser `null` y el mensaje pide únicamente los datos necesarios para desbloquear.
- Si `decision` es `corregir`, entrega el texto completo ya corregido, no solo recomendaciones.
- Si `decision` es `aprobar`, conserva el texto final y explica que está listo para revisión y firma de la persona.
- No incluyas cadenas de pensamiento, probabilidades de éxito ni una supuesta decisión judicial.
- No introduzcas marcadores como `[FECHA]` en un documento aprobado.
