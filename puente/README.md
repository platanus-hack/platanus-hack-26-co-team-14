# El puente

WhatsApp (Kapso) ↔ voz (ElevenLabs) ↔ el cerebro.

**El puente no decide nada del negocio.** Recibe el audio, lo transcribe, se lo
pasa al backend, y hace exactamente lo que el backend le conteste.

```
usuaria ──audio──> Kapso ──webhook──> PUENTE ──mensaje──> CEREBRO
usuaria <──voz──── Kapso <──envío──── PUENTE <─{responder}─ CEREBRO
```

En este repo el cerebro es `canal/cerebro.py`, y corre **en el mismo proceso**:
`app.py` lo enchufa al arrancar. No hay salto HTTP entre los dos.

El contrato de abajo es el mismo en los dos casos. Si algún día el backend se
va a otro servicio, se define `BACKEND_URL` y el puente empieza a llamarlo por
HTTP sin que haya que tocar nada más.

---

## 1. El contrato

### `POST {BACKEND_URL}/mensaje` — o `cerebro.responder(mensaje)`

Cada vez que la usuaria manda algo, el backend recibe esto. Por HTTP, y si
configuraste `BACKEND_TOKEN`, llega como `Authorization: Bearer <token>`.

**Recibe:**

```json
{
  "telefono": "573001112233",
  "mensaje_id": "wamid.HBgMNTczMDAx...",
  "tipo": "audio",
  "texto": "buenos días, la EPS no me ha entregado la insulina",
  "timestamp": "1730093100",
  "transcripcion": {
    "texto": "buenos días, la EPS no me ha entregado la insulina",
    "duracion": 12.4,
    "confianza": 0.93,
    "idioma": "spa",
    "baja_confianza": false,
    "texto_kapso": "buenos dias la eps no me ha entregado la insulina"
  }
}
```

- `tipo` es `"audio"` o `"text"`.
- `texto` ya viene transcrito. **Usa este campo y ya**; no tienes que tocar audio.
- `transcripcion` es `null` cuando el mensaje llegó escrito.
- `baja_confianza: true` significa que el STT no se fio. Conviene repreguntar
  antes de dar por bueno un dato (cédula, EPS, fechas).
- `texto_kapso` es la transcripción que hace Kapso por su cuenta. Está ahí para
  comparar; puedes ignorarla.

**Devuelves** una lista de cosas que el puente debe mandarle a la usuaria:

```json
{
  "responder": [
    { "tipo": "texto", "texto": "Entendí que le negaron la insulina." },
    { "tipo": "audio", "texto": "Le repito lo que entendí para que me confirme." },
    { "tipo": "documento",
      "url": "https://tu-backend/docs/abc.pdf",
      "nombre": "tutela.pdf",
      "descripcion": "Su tutela lista para radicar" }
  ]
}
```

Se ejecutan en orden. Tipos disponibles:

| tipo | campos | qué hace |
|---|---|---|
| `texto` | `texto` | mensaje de texto normal |
| `audio` | `texto`, `voice_id` (opcional) | genera la voz con ElevenLabs y la manda como nota de voz |
| `documento` | `url`, `nombre`, `descripcion` (opcional) | manda un PDF. La URL debe ser pública |

Devolver `{"responder": []}` es válido: no se manda nada.

Además de `url`, una acción `documento` acepta:

| campo | qué es |
|---|---|
| `archivo` | ruta en disco. El puente lee los bytes y los sube a Kapso |
| `contenido_b64` | los bytes en base64, para un backend remoto |

Las dos primeras son las que sirven en serverless: el archivo queda en Kapso,
no en un disco que desaparece en cuanto la función responde. Es lo que usa
`canal/orquestador.py` para mandar la tutela.

> Si el backend se cae o tarda más de `BACKEND_TIMEOUT`, el puente le avisa a la
> usuaria de una falla técnica en vez de dejarla en silencio.
> Sin `BACKEND_URL` y sin cerebro registrado, el puente responde en **eco**
> (repite lo que entendió, en texto y en voz). Sirve para probar el canal solo.

---

## 2. Endpoints que el puente te ofrece

Todos piden `Authorization: Bearer {API_TOKEN}`.

### `POST /api/enviar` — mandar algo cuando tú quieras

Para recordatorios, avisos de vencimiento de términos, lo que sea. No hace
falta que la usuaria haya escrito.

```bash
curl -X POST https://tu-puente.vercel.app/api/enviar \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"telefono":"573001112233","tipo":"audio",
       "texto":"Le recuerdo que mañana se vence el plazo de su EPS."}'
```

Varias de una:

```json
{ "telefono": "573001112233",
  "acciones": [
    {"tipo": "texto", "texto": "Su documento está listo."},
    {"tipo": "documento", "url": "https://...", "nombre": "tutela.pdf"}
  ] }
```

### `POST /api/voz` — texto a audio

Con `telefono` lo envía por WhatsApp; sin `telefono` te devuelve el archivo.

```bash
curl -X POST https://tu-puente.vercel.app/api/voz \
  -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"texto":"Buenos días"}' --output voz.ogg
```

### `POST /api/transcribir` — audio a texto

```bash
curl -X POST https://tu-puente.vercel.app/api/transcribir \
  -H "Authorization: Bearer $API_TOKEN" -F "archivo=@nota.ogg"
```

```json
{"texto": "...", "duracion": 12.4, "confianza": 0.93, "idioma": "spa"}
```

### `GET /api/voces` — voces disponibles

Para escoger el `ELEVENLABS_VOICE_ID`.

### `GET /salud` — diagnóstico (sin token)

Dice si faltan llaves, en qué modo corre, cómo está hablando con el backend
(`backend_modo`), y **la URL exacta que hay que pegar en Kapso** (campo
`pegar_en_kapso`).

### `GET /health` — el estado del cerebro (sin token)

Si la extracción tiene llave, qué plantillas hay cargadas y cuántas
conversaciones están abiertas en esta instancia.

---

## 3. Endpoints internos (no los llames)

| Ruta | Qué es |
|---|---|
| `POST /webhooks/whatsapp` | lo llama Kapso. Responde en milisegundos |
| `POST /webhooks/kapso` | la misma, con el nombre viejo |
| `POST /tareas/procesar` | segunda fase. Protegido con `API_TOKEN` |
| `GET /media/{nombre}` | sirve audio generado. Solo fuera de serverless |

### Por qué hay dos fases

Kapso exige **200 OK en menos de 10 segundos** y reintenta a los 10 s, 40 s y
90 s. Si te pasas, la usuaria recibe todo dos veces. Pero STT + backend + TTS
tarda más que eso.

- `MODO_PROCESO=background` — el webhook encola y el mismo proceso sigue
  trabajando. Sirve donde el servidor es persistente (local, Render).
- `MODO_PROCESO=http` — el webhook se auto-invoca por HTTP contra
  `/tareas/procesar` y responde al instante. **Es lo único que funciona en
  serverless**, donde el proceso muere en cuanto responde.

Se detecta solo: si hay `VERCEL` en el entorno usa `http`, si no `background`.

---

## 4. Arrancar en local

La llave de ElevenLabs necesita **dos** permisos marcados al crearla:
`Text to Speech` y `Speech to Text`. Con solo lectura, `/v1/voices` responde 200
pero TTS y STT devuelven `401 missing_permissions`.

El `.env` manda sobre el entorno (`load_dotenv(override=True)`): si hay una
`ELEVENLABS_API_KEY` vieja exportada en el sistema, ya no le gana al `.env`.

```bash
pip install -r requirements.txt
cp .env.example .env          # rellenar las 4 llaves

python -m puente.probar --voces    # escoger la voz
python -m puente.probar           # comprobar que TTS y STT sirven
pytest                            # 51 pruebas, sin red
python arrancar.py                # servidor + túnel + URL para Kapso
```

`arrancar.py` levanta todo y te imprime la URL que hay que pegar en Kapso.
Esa URL **cambia en cada arranque** (es un túnel gratis).

### En el sandbox de Kapso

Kapso responde `403 Active sandbox session required` hasta que **tú le escribas
primero** al número del sandbox desde tu WhatsApp. La sesión caduca; si vuelve
el 403, le escribes otra vez.

---

## 5. Desplegar en Vercel

```
├── api/index.py       ← entrypoint (importa app.py de la raíz)
├── vercel.json        ← solo maxDuration 60s. SIN rewrites (ver abajo)
├── .vercelignore      ← que no suba .env
├── requirements.txt
└── puente/
```

En **Project Settings → Environment Variables** hay que meter:

```
KAPSO_API_KEY           KAPSO_PHONE_NUMBER_ID
ELEVENLABS_API_KEY      ELEVENLABS_VOICE_ID
ANTHROPIC_API_KEY       ← sin ella el canal oye pero no entiende
API_TOKEN               ← obligatorio en producción, no dejarlo vacío
PUBLIC_BASE_URL         ← https://tu-proyecto.vercel.app, sin barra final
MODO_PROCESO=http
```

`PUBLIC_BASE_URL` hay que marcarla **no sensible**: Vercel rechaza como secreta
cualquier variable que empiece por `PUBLIC` (`invalid_visibility`). Con el CLI:
`vercel env add PUBLIC_BASE_URL production --no-sensitive`.

Webhook en Kapso: `https://tu-proyecto.vercel.app/webhooks/whatsapp`

### Tres cosas que hay que vigilar en Vercel

0. **No poner `rewrites` en `vercel.json`.** Con el preset de FastAPI, Vercel ya
   manda *todas* las rutas al entrypoint. Y desde 2026 un rewrite interno en un
   proyecto de backend enruta usando la ruta **de destino**: un
   `{"source": "/(.*)", "destination": "/api/index"}` hace que la app reciba
   siempre el path `/api/index`, que no existe, y todo responde
   `{"detail":"Not Found"}` — incluida `/salud`. El build lo avisa:
   *"Internal rewrites in backend framework projects now route requests using
   the rewritten destination path."*


1. **El presupuesto de tiempo.** `maxDuration` está en 60 s (el tope de Hobby;
   con Fluid Compute son 300 s). STT ~3 s + backend + TTS ~2 s + envío ~1 s
   cabe de sobra, pero si el backend tarda mucho, súbelo o activa Fluid Compute.
2. **La idempotencia es por instancia.** El puente descarta reintentos de Kapso
   con `X-Idempotency-Key`, pero en serverless la memoria no se comparte entre
   invocaciones. Si aparecen mensajes duplicados, hay que llevar esa marca a
   una tabla del backend.

> En Render nada de esto aplica: `MODO_PROCESO=background`, servidor
> persistente y URL fija. Es más simple, si quieren cambiar.

---

## 6. Archivos

| Archivo | Qué hace |
|---|---|
| `config.py` | lee `.env`, detecta plataforma y modo |
| `kapso.py` | firma HMAC, descarga media, envía texto/audio/documento |
| `voz.py` | ElevenLabs STT (Scribe) y TTS |
| `backend.py` | cliente del backend, con eco de respaldo |
| `app.py` | FastAPI: webhook, tareas y API |
| `probar.py` | pruebas sin WhatsApp |

El que enchufa el puente al cerebro es `app.py` de la raíz, no ninguno de
estos: el puente no importa nada de `canal/`, `core/` ni `juridico/`, y así
sigue siendo un canal y no medio backend.
