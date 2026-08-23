# Dataset estructurado de jurisprudencia colombiana sobre tutela y derecho a la salud

Primera versión · Corte Constitucional de Colombia · Proyecto Tutela Voz

---

## Qué es

Un pipeline ETL que extrae providencias de tutela en salud desde la fuente oficial, las
convierte en datos estructurados y los deja listos para análisis estadístico, búsqueda
semántica y RAG.

```
FUENTE OFICIAL → EXTRACT → RAW → TRANSFORM → VALIDATE → JSON → BD / RAG
```

Sin dependencias externas: corre con la librería estándar de Python.

---

## Fuente y método

**Relatoría de la Corte Constitucional de Colombia**
`https://www.corteconstitucional.gov.co/relatoria/`

Fuente única y primaria. No se usaron blogs, agregadores comerciales, prensa ni bases privadas.

### Mecanismo de extracción

No es scraping de HTML renderizado. Se usa el **canal oficial de exportación** del buscador
de la Relatoría: el mismo endpoint que ejecuta su botón "Descargar Excel".

```
GET https://www.corteconstitucional.gov.co/relatoria/buscador_new/
    ?searchOption=texto
    &fini=YYYY-MM-DD&ffin=YYYY-MM-DD
    &buscar_por="derecho a la salud"
    &aggs_prov_proceso_terminos[]=prov_proceso_terminos|Acciones de Tutela
    &aggs_prov_tipo[]=prov_tipo|Tutela
    &maxprov=250&slop=1&accion=search_excel&tipo=json
```

Devuelve JSON de Elasticsearch. Sin autenticación, sin token, sin CAPTCHA.
El texto completo se descarga de `/relatoria/{url_relatoria}`.

### Cumplimiento

Verificación de `robots.txt` (22 de agosto de 2026):

| Ruta | Estado | Uso |
|---|---|---|
| `/relatoria/` | **Allow** explícito | sí — buscador y documentos |
| `/API/` | Disallow | no se toca |
| `/sentencias/` | Disallow | **no se usa**, aunque espeja los mismos textos |

El texto de una sentencia existe en dos rutas: una prohibida y otra permitida. El ETL usa
solo la permitida. Además: 1 petición cada 2 segundos, secuencial, `User-Agent` identificable,
caché en disco. No se evade ningún control.

---

## Resultados

| Etapa | Documentos |
|---|---|
| Candidatos descubiertos (2019–2025, deduplicados) | 2044 |
| Relevantes tras filtro temático de salud | 763 |
| Con texto completo y extracción profunda | 150 |
| **Válidos contra el JSON Schema** | **150 / 150** |
| Descartados | 1281 |
| Providencias con expedientes acumulados | 29 |

### Distribución de resultados jurídicos

Leídos del texto oficial del RESUELVE, no inferidos.

| Resultado | Providencias | % |
|---|---|---|
| MULTICASO | 19 | 12.7% |
| CONCEDE | 18 | 12.0% |
| IMPROCEDENTE | 17 | 11.3% |
| CARENCIA_ACTUAL_DE_OBJETO | 16 | 10.7% |
| CONCEDE_PARCIALMENTE | 16 | 10.7% |
| HECHO_SUPERADO | 16 | 10.7% |
| MIXTO | 16 | 10.7% |
| NIEGA | 16 | 10.7% |
| OTRO | 16 | 10.7% |

### Por qué se descartaron documentos

| Motivo | Documentos |
|---|---|
| fuera del alcance tematico (salud): 0 marcadores | 887 |
| fuera del alcance tematico (salud): 1 marcadores | 393 |
| sin texto de RESUELVE en el indice oficial | 1 |

---

## Reglas de calidad

1. **No se inventa nada.** Cada dato interpretado guarda el fragmento textual que lo respalda,
   su rango de caracteres (`char_span`) y la regla que lo produjo. Verificable contra el
   documento oficial.
2. **Tres estados, no dos.** `true` = la providencia lo afirma · `false` = afirma lo contrario ·
   `null` = no dice nada. Nunca se rellena con `false` por defecto.
3. **El resultado se lee, no se infiere.** Sale del campo oficial `prov_resuelve`, parseado por
   numeral resolutivo. El parser distingue `CONFIRMAR la sentencia que NEGÓ` de un fallo favorable.
4. **Los hechos se leen solo de ANTECEDENTES**, para no confundirlos con la doctrina general de
   las CONSIDERACIONES ni con lo que decidió la Corte.
5. **Varios expedientes no se colapsan.** Si una providencia acumula expedientes con suertes
   distintas, el resultado es `MULTICASO` y se guarda el resultado por expediente.
6. **Sin LLM.** Fase 1 completamente determinista y auditable (`provenance.llm_used = false`).

### Taxonomía de resultados

`CONCEDE` · `CONCEDE_PARCIALMENTE` · `NIEGA` · `IMPROCEDENTE` · `CARENCIA_ACTUAL_DE_OBJETO` ·
`HECHO_SUPERADO` · `HECHO_NO_SUPERADO` · `DESISTIMIENTO` · `MULTICASO` · `OTRO` · `MIXTO`

`MIXTO` es una extensión propia: un solo expediente con numerales de resultados distintos y
ninguno de amparo.

`favorable_result` mapea únicamente CONCEDE/CONCEDE_PARCIALMENTE → `true` y NIEGA/IMPROCEDENTE
→ `false`. Los demás quedan en `null`: **no se asume que carencia de objeto o hecho superado
sean "buenos" o "malos"**.

---

## Limitaciones

1. **La muestra profunda no es aleatoria.** Está estratificada a propósito por resultado para
   cubrir todos los desenlaces. **No sirve para estimar frecuencias poblacionales.** Para eso
   está `capa_a_metadatos.json`, con las 763 relevantes sin estratificar.
2. **Extracción determinista.** Auditable y reproducible, pero deja muchos nulls en hechos finos.
3. **Providencias acumuladas: hechos no separables.** Se atribuye el resultado por expediente,
   pero los hechos quedan a nivel de documento.
4. **Urgencia y perjuicio irremediable se leen solo de ANTECEDENTES.** La Corte suele discutirlos
   en CONSIDERACIONES, lo que explica sus nulls altos. Es deliberado: mezclarlos confundiría los
   hechos del caso con el análisis del tribunal.
5. **Nombres anonimizados** por la propia Corte en providencias con datos sensibles de salud.
6. **Cobertura 2019–2025.** El índice oficial llega hasta 1992.

### Variables con más nulls

| Variable derivada | % null |
|---|---|
| `orphan_disease` | 98.3% |
| `vital_risk` | 85.1% |
| `petition_answered` | 82.6% |
| `administrative_barrier` | 79.3% |
| `delay_involved` | 79.3% |
| `irreparable_harm` | 74.4% |
| `previous_petition` | 72.7% |
| `serious_illness` | 71.9% |
| `urgent_case` | 71.9% |
| `service_denied` | 67.8% |
| `procedure_involved` | 62.0% |
| `medication_involved` | 53.7% |

---

## Archivos generados

| Archivo | Contenido |
|---|---|
| `dataset_tutela_salud.json` | dataset principal, una providencia por registro |
| `dataset_tutela_salud.jsonl` | una línea por providencia, para carga a BD |
| `flat_cases.csv` | tabla plana por caso (217 filas, 43 columnas) |
| `capa_a_metadatos.json` | las 763 relevantes con metadatos y RESUELVE |
| `informe_calidad.json` | cobertura, nulls, descartes |
| `schema/tutela_salud.schema.json` | contrato del dataset (JSON Schema 2020-12) |

## Cómo ejecutarlo

```bash
python3 run_etl.py                 # corrida completa
python3 run_etl.py --deep 40       # solo 40 providencias con texto completo
python3 run_etl.py --discover-only # solo descubrimiento
```

Idempotente y reanudable: lo descargado queda en caché, así que una segunda corrida no le pide
nada a la Corte (se completa en ~90 segundos). La extracción original tomó ~45 minutos.

---

## Para qué sirve

Responder con evidencia dos preguntas:

- ¿Qué caracteriza a los casos de tutela en salud que terminan **favorables**?
- ¿Qué caracteriza a los que terminan **negados, improcedentes o sin objeto**?

Y con eso: mejorar las preguntas que Tutela Voz le hace al paciente, y mejorar la estructura de
los documentos jurídicos que genera.
