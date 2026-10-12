# K'ab Local Ingest V1

Ingesta local segmentada de medios desde el remitente K'ab (Android) hacia
esta estación, por TLS en la red local. Todo el pipeline es local: sin nube,
sin base de datos remota, sin cola externa, sin LLM externo
(`ALLOW_EXTERNAL_LLM=false` en todo el camino).

Estado: **congelado (V1)**. Receptor deshabilitado por defecto.

## Componentes

| Proceso | CLI | Función |
| --- | --- | --- |
| Receptor | `transcript-kab-ingest` | API TLS `/kab/v1/*`, recibe chunks, arma segmentos |
| Worker | `transcript-kab-ingest-worker` | Escanea `ready/`, muxea, transcribe, consolida |
| Cert | `transcript-kab-ingest-cert` | Cert autofirmado local + bearer token de alta entropía |

Paquete: `src/transcript_pipeline/kab_ingest` (proceso separado del dashboard).

## Configuración (`KAB_INGEST_*`)

| Variable | Default | Nota |
| --- | --- | --- |
| `KAB_INGEST_ENABLED` | `false` | El receptor nunca arranca implícitamente |
| `KAB_INGEST_HOST` | sin setear | Solo loopback (127.0.0.0/8, ::1), RFC1918 IPv4 (10/8, 172.16/12, 192.168/16) o ULA IPv6 (fc00::/7). Se rechazan wildcard, públicas, link-local y nombres DNS |
| `KAB_INGEST_PORT` | `5443` | 1024-65535 |
| `KAB_INGEST_TOKEN` | sin setear | Bearer token; generado por el CLI de cert, nunca en Git |
| `KAB_INGEST_CERT` / `KAB_INGEST_KEY` | sin setear | PEM obligatorio; sin TLS no hay arranque |
| `KAB_INGEST_MAX_CHUNK_MB` | `8` | Límite por chunk |
| `KAB_INGEST_MAX_SESSION_GB` | `50` | Límite acumulado por sesión |
| `KAB_INGEST_ROOT` | `DATA_ROOT/kab-inbox` | Raíz de almacenamiento (gitignored) |

`transcript-kab-ingest --check` valida la postura sin servir.

## API (`/kab/v1`, autenticación en todos los endpoints)

Todas las respuestas de error son JSON uniforme
`{"error": {"code": ..., "message": ...}}`. Autenticación Bearer con
comparación en tiempo constante; 401 uniforme; el token jamás se registra
en logs ni respuestas. Ninguna respuesta contiene rutas del sistema de
archivos: el estado se expresa con índices, hashes, tamaños y nombres de
estado.

- `POST /kab/v1/sessions` — `{schemaVersion:1, sessionId, title, createdAt,
  segmentDurationSec, requiredTracks}` (`video`, `audio` o ambos).
  Idempotente con metadatos idénticos; `409` si difieren.
- `GET /kab/v1/sessions/{id}` — estado seguro: segmentos
  completados/pendientes/fallidos, índices de chunks recibidos, estados
  `RECEIVED/PROCESSING/PROCESSED/FAILED`, sin rutas.
- `PUT /kab/v1/sessions/{id}/segments/{segmentIndex}/{track}/chunks/{chunkIndex}`
  — cuerpo crudo en streaming con `X-Chunk-SHA256` y `X-Chunk-Size`
  (ambos obligatorios y consistentes con `Content-Length`). Temporal +
  SHA-256 en streaming + fsync + reemplazo atómico. Mismo hash → idempotente;
  contenido distinto en el mismo índice → `409`; cuerpo corrupto nunca se
  persiste.
- `POST /kab/v1/sessions/{id}/segments/{segmentIndex}/{track}/complete` —
  `{schemaVersion, totalChunks, sizeBytes, sha256, extension, durationMs,
  startOffsetMs}`. Extensiones por allowlist estricto por pista (video:
  `.mp4/.mkv/.mov/.webm`; audio: `.wav/.m4a/.mp3/.flac/.ogg/.opus`).
  Ensambla en orden exacto de chunks, verifica tamaño y hash, y solo
  entonces renombra atómicamente a `segments/segment-NNNNNN.{track}{ext}`.
  El marcador `ready/segment-NNNNNN.ready.json` se crea solo cuando todas
  las pistas requeridas del segmento están persistidas y verificadas
  (`startOffsetMs`/`durationMs` deben coincidir entre pistas).
- `POST /kab/v1/sessions/{id}/complete` — `{schemaVersion,
  expectedSegmentCount, endedAt, reason}`. Si los índices `0..n-1` están
  todos verificados como `PROCESSED`, consolida y responde
  `COMPLETED`; si falta alguno responde `WAITING_FOR_SEGMENTS`. Idempotente;
  parámetros distintos sobre una finalización previa → `409`.

Los IDs de sesión cumplen `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`; los índices
son enteros no negativos; las rutas del servidor siempre son generadas por
el servidor.

## Almacenamiento

```
kab-inbox/{sessionId}/
    session.json                    creado por el receptor (atómico)
    state.json                      escrito solo por el worker (atómico)
    chunks/NNNNNN/{video,audio}/    chunks crudos (atómicos)
    segments/                       medios ensamblados + .meta.json
    ready/segment-NNNNNN.ready.json marcadores de trabajo (atómicos)
    processing/  failed/  completed/
```

Toda transición de estado es archivo temporal + fsync + `os.replace` en el
directorio destino: un crash nunca deja estados a medias visibles.

## Worker

Local y de una sola máquina. Escanea y reconcilia `ready/`, procesa
incrementalmente mientras se siguen subiendo segmentos posteriores (sin
límite de duración de sesión), y es reanudable tras reinicios:

- nunca procesa dos veces un `PROCESSED`;
- un `PROCESSING` huérfano (crash) se reintenta exactamente una vez; si
  falla de nuevo queda `FAILED` (sin bucles infinitos);
- un segmento ensamblado sin marcador `ready` (crash entre escrituras) se
  reconcilia y encola de nuevo;
- los originales (chunks, medios ensamblados) nunca se auto-borran.

Por segmento: video solo o audio solo se transcribe directo; video+audio
externo se muxea con FFmpeg (argv array, sin shell; `-map 0:v:0 -map 1:a:0`,
video en copia de flujo, audio a AAC; error de FFmpeg ⇒ segmento `FAILED`,
nunca se sustituye el audio silenciosamente). La transcripción reutiliza
`SimpleScanProcessor` (Whisper local, detección de idioma, keyframes, OCR,
`FileTracker`, y documentación existente). Los timestamps de sesión son
`startOffsetMs/1000 + timestamp local del medio`.

Tras cada segmento procesado se regeneran atómicamente:

```
CarpetaTranscripciones/kab/{sessionId}/SESSION_TRANSCRIPT.txt
CarpetaTranscripciones/kab/{sessionId}/SESSION_SEGMENTS.json
CarpetaTranscripciones/kab/{sessionId}/SESSION_MANIFEST.json
```

`SESSION_SEGMENTS.json` se ordena por (índice de segmento, timestamp local)
y cada entrada lleva provenance `sourceSegmentIndex/localStart/localEnd`.
Sin borrado difuso ni reescritura por LLM: el texto se cita verbatim.

Al completar la sesión, la consolidación reutiliza los
`DocumentationSource`/`ProceduralStep` ya producidos por segmento,
preservando evidencia/confianza/`evidence_source`/`transcript_ref`/
`ocr_text`/`visual_description`/`reviewed`, aplicando offsets y orden
global determinista e IDs deterministas, y escribe vía las funciones
existentes `write_manual()`/`write_ai_package()`:

```
kab-inbox/{sessionId}/completed/manual/{MANUAL.md,MANUAL.pdf,steps.json,metadata.json,assets}
kab-inbox/{sessionId}/completed/ai-package/{manifest.json,steps.json,chunks.jsonl,knowledge.md,assets}
kab-inbox/{sessionId}/completed/session.complete.json   # rutas relativas seguras + booleanos de disponibilidad
```

La consolidación no inventa instrucciones ni llama a ningún LLM; el estado
de sesión pasa a `COMPLETED`.

## Provisionamiento de credenciales

```
transcript-kab-ingest-cert [--runtime-dir DIR] [--show-token]
```

Escribe en el directorio runtime (fuera de Git,
`kab-inbox/.runtime` bajo `DATA_ROOT` por defecto): cert autofirmado local,
llave privada y token bearer de 48 bytes CSPRNG. Solo imprime ruta del
cert, fingerprint SHA-256 y ruta del archivo de token; el valor del token
se imprime únicamente con `--show-token` explícito.

## Invariantes de seguridad

- Límites por chunk y por sesión con `Content-Length` estricto y lectura en
  streaming; timeout de lectura.
- IDs/extensión/pistas validados; solo rutas generadas por el servidor.
- Autenticación bearer en tiempo constante; 401 uniforme; token nunca en
  logs.
- Arranque solo con TLS 1.2+ y credenciales presentes; bind solo en
  loopback/RFC1918/ULA.
- Estado atómico en cada transición; sin rutas absolutas en respuestas;
  sin `shell=True`.
- El dashboard conserva su seguridad localhost, `SafePathResolver`,
  `PrivacyGuard`, LLM remoto deshabilitado por defecto y sus tests de
  Host/Origin/token sin cambios.

## Pruebas deterministas

`tests/test_kab_ingest_*.py` cubren T01-T48: default deshabilitado;
política de bind aceptada/rechazada; rechazo sin TLS; auth 401 uniforme y
token fuera de logs; seguridad de IDs/rutas/pistas/extensiones; SHA
válido/erróneo, idempotencia/conflicto de duplicados, límites de tamaño;
orden/pista faltante/tamaño/hash de segmentos; marcador ready atómico;
restart/reconcilio/stale sin duplicados; video/audio/mux/fallo FFmpeg;
offsets/orden/idempotencia de transcripciones; finalización con espera e
idempotencia; consolidación sin LLM con evidencia/offsets/orden;
manual/AI/PDF cuando hay dependencias; y una prueba offline solo-loopback
más un E2E sintético (2 videos + 2 audios generados con FFmpeg local, TLS
en loopback temporal) que afirma los outputs y el estado `COMPLETED`.
