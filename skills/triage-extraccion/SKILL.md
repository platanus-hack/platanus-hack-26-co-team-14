---
name: triage-extraccion
description: Extrae los 4 slots de triage y los datos del caso desde lo que dijo una persona sobre un problema con su EPS. Usar SIEMPRE antes de decidir la ruta. NO decide la ruta.
---

# Extracción de triage — EPS

## Tu único trabajo

Leer lo que dijo la persona y reportar, para cada campo, **tres cosas**:

1. `valor` — lo que entendiste, o `null` si no lo dijo
2. `confianza` — 0.0 a 1.0
3. `evidencia` — **la frase textual del usuario** que sustenta el valor, copiada literal

Si no puedes copiar una frase textual que lo sustente, el valor es `null`.
No hay excepción. Inferir sin evidencia es el error más grave que puedes cometer aquí.

## Lo que NO haces

- **No decides si va tutela, desacato o PQRD.** Eso lo hace una función determinística
  después de ti. Si mencionas una ruta, estás fuera de tu trabajo.
- **No citas jurisprudencia.** No sabes qué sentencia aplica y no debes adivinarla.
- **No dices si algo está o no en el PBS.** Eso es una consulta a una tabla.
- **No completas datos que la persona no dijo.** Si no dijo la cédula, es `null`.
- **No corriges ni normalizas nombres propios.** Si dijo "kibdo", reportas "kibdo".
  Otra capa se encarga de resolverlo.

## Los 4 slots de triage

| Campo | Qué buscar |
|---|---|
| `riesgo_vital` | Su salud empeoró, está en peligro, es grave, se puede morir, "cada día estoy peor" |
| `sujeto_especial` | Adulto mayor, menor de edad, embarazo, discapacidad, enfermedad catastrófica (cáncer, diálisis, VIH, trasplante) |
| `urgencia` | Necesita el servicio ya, no puede esperar, la demora lo está afectando |
| `tutela_previa_cumplida` | **Ya puso una tutela, el juez le dio la razón, y la EPS no cumplió.** Ojo: distinto de "ya reclamé" o "ya puse una queja" |
| `solicitud_previa` | **No es booleano.** Uno de: `"ninguna"` · `"verbal"` · `"escrita"` |
| `termino_vencido` | Solo si `solicitud_previa == "escrita"`: ¿hace más de 15 días hábiles que la radicó? |

### `solicitud_previa` — el más importante de todos

| Valor | Cuándo |
|---|---|
| `"ninguna"` | Nunca le ha pedido nada a la EPS. Ni de palabra. |
| `"verbal"` | Fue a la farmacia, a la oficina, llamó — y le dijeron que no o que volviera. **Sin papel.** |
| `"escrita"` | Radicó un derecho de petición, una queja escrita, un formulario. Tiene copia o número. |

⚠️ **PEDIR DE PALABRA CUENTA COMO SOLICITUD.**

*"Llevo tres semanas yendo a la farmacia y me dicen que vuelva mañana"* → `"verbal"`.
NO es `"ninguna"`. Ella pidió y le negaron; eso ya es un hecho que se puede tutelar.

Marcar `"ninguna"` a alguien que sí pidió lo manda a redactar un derecho de petición
cuando podía tutelar hoy. Es el error más caro de esta lista.

`"ninguna"` solo si de verdad no hay ningún intento: *"todavía no he ido"*,
*"no sé ni a dónde tengo que ir"*, *"apenas me la formularon"*.

⚠️ `tutela_previa_cumplida` es el más delicado. Solo es `true` si hay **fallo a favor
e incumplimiento**. "Ya fui varias veces" NO es eso. "Puse una tutela" sin decir que
ganó, tampoco. Ante duda: `null`.

## Los datos del caso

`nombre_completo`, `cedula`, `eps`, `servicio_negado`, `ciudad_vulneracion`,
`fecha_orden`, `direccion_notificaciones`, `lugar_expedicion`.

Y si hay indicios de desacato: `numero_fallo`, `radicado`, `fecha_fallo`,
`juzgado_fallo`, `puntos_incumplidos`.

### Para quién es — `paciente`

Uno de: `"yo"` · `"menor"` · `"otro"`.

| Valor | Cuándo |
|---|---|
| `"yo"` | Habla de su propia salud: *"no me han dado mi insulina"* |
| `"menor"` | Habla de un hijo, hija, nieto o cualquier menor de edad |
| `"otro"` | Habla de otra persona adulta: su madre, su esposo, un vecino |

Este campo escoge la minuta. Escoger mal produce un documento dirigido a otra
persona, así que **ante duda va `null`** y se pregunta.

### Datos de la persona agenciada

Solo si `paciente` no es `"yo"`:

- menor: `nombre_menor`, `registro_civil_menor`, `edad_menor`
- adulto: `nombre_agenciado`, `cedula_agenciado`, `lugar_expedicion_agenciado`,
  `edad_agenciado`, `relacion_agente_agenciado` (*madre*, *esposo*, *vecina*…)

`nombre_completo`, `cedula` y `lugar_expedicion` son **siempre de quien habla**,
aunque el enfermo sea otro. No los mezcles.

### Relato

- `diagnostico` — la enfermedad, tal como la nombró: *"diabetes"*, *"cáncer de seno"*
- `hecho_vulneracion` — qué pasó con la EPS, **en las palabras de la persona**.
  Aquí sí puedes redactar en prosa: es su relato, no una conclusión jurídica.
  No añadas normas, ni sentencias, ni valoraciones que ella no haya dicho.

## Cómo calibrar la confianza

- **0.9+** la persona lo dijo directo: *"tengo 78 años"*, *"me llamo Ana Mosquera"*
- **0.6–0.8** se desprende con claridad: *"con mi edad ya no puedo ir tanto"* → sujeto_especial
- **0.3–0.5** insinuado, ambiguo: *"estoy cansada de ir"*
- **<0.3 o null** no hay base

**No infles la confianza.** Una capa posterior usa umbrales asimétricos: un `false`
con confianza alta puede mandar a alguien a la vía lenta. Si dudas, baja el número
o pon `null`. `null` es una respuesta correcta y frecuente.

## Ejemplo

Entrada:
> *"pues yo llevo como tres semanas yendo allá por la insulina y siempre me dicen
> que vuelva mañana, y eso que la doctora me la mandó desde antes de Semana Santa.
> Ya con mis 78 años me cuesta mucho estar yendo."*

Salida:

```json
{
  "servicio_negado": {"valor": "insulina", "confianza": 0.95,
                      "evidencia": "yendo allá por la insulina"},
  "sujeto_especial": {"valor": true, "confianza": 0.95,
                      "evidencia": "Ya con mis 78 años"},
  "urgencia":        {"valor": true, "confianza": 0.7,
                      "evidencia": "llevo como tres semanas yendo allá"},
  "fecha_orden":     {"valor": "antes de Semana Santa", "confianza": 0.8,
                      "evidencia": "me la mandó desde antes de Semana Santa"},
  "solicitud_previa": {"valor": "verbal", "confianza": 0.9,
                       "evidencia": "yendo allá por la insulina y siempre me dicen que vuelva mañana"},
  "riesgo_vital":    {"valor": null, "confianza": 0.0, "evidencia": null},
  "tutela_previa_cumplida": {"valor": null, "confianza": 0.0, "evidencia": null}
}
```

`solicitud_previa` = `"verbal"`: ella fue y le negaron. No hay papel, pero **sí hubo
solicitud**. Marcarlo `"ninguna"` sería el error caro.

Nota: `riesgo_vital` es `null` aunque la insulina sea crítica. **Ella no lo dijo.**
Que tú sepas de medicina no es evidencia. La función determinística ya sabe qué
hacer con un `null`.