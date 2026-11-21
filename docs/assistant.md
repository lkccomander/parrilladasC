# Lenguaje natural y control de Admin

El módulo `backend/src/parrilladas/modules/assistant/` valida intención y datos
del evento. `integrations/vertex_ai/` utiliza Google Gen AI, JSON estructurado,
thinking mínimo, un solo intento y 512 tokens de salida. El proyecto, modelo,
ubicación y timeout son configurables. No utiliza Search, Maps ni herramientas externas.

## Activación en WhatsApp

Se requieren tres condiciones: `NATURAL_LANGUAGE_ENABLED=true` en el API,
`CONVERSATION_WORKER_ENABLED=true` con configuración completa del canal, y la
preferencia de lenguaje natural guardada por un Admin. El API rechaza activar
procesamiento de modelos sin el worker persistente. Si la autenticación del modelo
no puede configurarse, conserva el modo guiado y no informa IA activa.

`CONVERSATION_PROCESSING_START_AT` debe ser una fecha/hora con zona, fijada al
activar el piloto. El worker no recupera filas anteriores a esa fecha y descarta
mensajes cuyo timestamp de Meta sea anterior. No se reinicia este valor al
redesplegar: así se recupera trabajo pendiente creado durante una interrupción.

El webhook verifica firma, WABA y `phone_number_id`, guarda el lote en PostgreSQL
y responde sin esperar a Google ni a Meta. Un worker del API consulta el inbox y
outbox persistidos. Un lock transaccional de PostgreSQL serializa el procesamiento
entre réplicas para este negocio. La configuración verificada del canal corresponde
al único tenant activo, `parrilladas`; el modelo y el remitente no eligen el tenant.
No habilitar otros negocios sin resolver pertenencia y aislar también sus conversaciones.

El worker prepara la respuesta y marca el evento procesado en una transacción.
Los envíos pendientes se recuperan tras reinicios. Antes de llamar a Meta, persiste
`sending`; tras éxito guarda `sent`. Un fallo de resultado ambiguo queda
`uncertain`, pausa la conversación y requiere revisión operativa. Ni `sending` ni
`uncertain` se reenvían automáticamente, y bloquean envíos posteriores de esa
conversación. Un proceso interrumpido durante el envío puede dejar `sending`;
revisarlo con el operador y con el estado de Meta antes de cualquier nuevo intento.
No existe garantía de entrega exactamente una vez ni un botón de reintento manual.

Las conversaciones pausadas no llaman al modelo. Una pausa cancela respuestas
pendientes, salvo el aviso de derivación que produjo la propia pausa. La llamada
externa ya iniciada puede completarse; la pausa no puede retirar mensajes enviados.
Las solicitudes cerradas siguen cerradas hasta una operación explícita del operador.
El worker no reanuda ni reinicia conversaciones por su cuenta.

## Captura y confirmación

Ambos modos comparten el primer mensaje de bienvenida del flujo guiado, con
la imagen, el texto y los tres botones originales. La bienvenida no llama a
Gemini y los reintentos del webhook no la duplican. Después del saludo el cliente
puede seleccionar «Solicitar cotización» o escribir directamente los datos.
La captura de fecha, invitados, ubicación y servicio puede hacerse en un solo
mensaje posterior a la bienvenida. El modelo propone datos; Python valida tipos, fecha completa con
año y evidencia literal, y preguntas de aclaración. No se exige presupuesto ni
tipo de evento. Los datos propuestos se guardan en el borrador de conversación.

Los estados `nl_collect`, `nl_review` y `nl_changes` distinguen datos faltantes,
revisión y correcciones. Una corrección no sustituye datos anteriores sin pulsar
**Aplicar cambios**. Después se vuelve al resumen; **Confirmar datos** es otra
acción explícita y cierra la solicitud. No se confirma precio, disponibilidad ni
reserva. Los precios, aprobación y envío de cotizaciones siguen siendo manuales.

Las conversaciones que ya estaban en una pregunta guiada conservan su flujo.
Las nuevas usan el modo efectivo guardado en Admin. Apagar la preferencia no
impide confirmar un borrador NL existente mediante botones; si necesita más
interpretación, ofrece preguntas literales sin IA o atención humana. Errores del
modelo y consultas sin conocimiento aprobado no pausan automáticamente el bot.
La derivación requiere petición explícita de una persona o selección de «Hablar con asesor».
Las pausas humanas previas y las solicitudes finalizadas conservan su estado.

## Admin

`/dashboard/assistant` y `GET/PATCH /assistant/preferences` requieren Admin activo.
El API usa Bearer JWT; las mutaciones y el formulario validan CSRF. La migración
`0005` conserva la preferencia, tenant y fecha/actor. Esta activación reutiliza el
esquema existente; no necesita crear tablas en el arranque.

El dashboard muestra **Modo guiado** y **Lenguaje natural**. La etiqueta usa
`active_mode` del API, combinando la preferencia con la disponibilidad del runtime.
Una preferencia encendida con gate/runtime apagado muestra **Activación pendiente**.
Si falla la consulta del estado, muestra **Modo sin verificar**. Admin nunca accede
al ORM, a PostgreSQL ni a las credenciales de Google.

## Comprobación sintética

Con el paquete y los locks instalados, puede comprobarse Google sin mensajes a
clientes ni PostgreSQL:

```powershell
$env:GOOGLE_CLOUD_PROJECT = "parrilladas-ai-pilot"
$env:GOOGLE_CLOUD_LOCATION = "global"
$env:GEMINI_MODEL = "gemini-3.5-flash-lite"
$env:VERTEX_CONNECTION_ENABLED = "true"
.\.venv\Scripts\python.exe -m parrilladas.modules.assistant.cli --check-connection
```

En desarrollo se usa ADC; en Railway, una cuenta de servicio exclusiva del API.
Las credenciales ADC personales se rechazan en producción. Consultar [Railway](railway.md).
La comprobación envía una solicitud sintética para 20 personas en Alajuela el 20 de
diciembre del próximo año. Genera consumo del modelo. Las alertas de USD 15/mes
no son un límite duro. El comando sin `--check-connection` conserva el gate
`NATURAL_LANGUAGE_ENABLED` y tampoco contacta a clientes.

## Respuestas comerciales controladas (Beta 1.03)

El [catálogo editable](../knowledge/README.md) contiene platos y cobertura nacional.
Se incluye en el wheel y la imagen de API; no se requiere una pantalla de menú en
Admin para editarlo. La recuperación inicial seleccionaba hechos por tema; desde
Beta 1.12 puede recuperar los hechos publicados mediante embeddings y pgvector.
Gemini clasifica la intención y el tema en un esquema cerrado;
Python responde mediante plantillas y hechos validados, nunca con texto comercial
libre generado por el modelo. Cada respuesta de catálogo identifica internamente
la fuente y su versión. El único negocio soportado es `parrilladas`; otro tenant
no puede consultar estos hechos. Antes de habilitar más canales se necesita el
mapeo y aislamiento multi-tenant completos.

- Menú: nombres de platos activos; no asumir paquetes, porciones o ingredientes.
- Cobertura: provincias documentadas; no implica fecha disponible ni traslado gratis.
- Preparación: cocinar en el lugar solo si lo indica el catálogo.
- Precios y disponibilidad: explicar revisión humana, sin cifras ni reservas.
- Alergias, pagos, cancelaciones y detalles no documentados: reconocer el límite y
  ofrecer un asesor. La oferta no deriva; el cliente debe seleccionarla.
- «Quiero más información»: ofrecer menú, cobertura o solicitud.
- Fuera de tema: recordar el alcance y ofrecer continuar, sin borrar el borrador.
- Fallo/JSON inválido: conservar datos y ofrecer «Continuar sin IA». El modo literal
  valida fecha ISO completa, entero positivo, ubicación y servicio, sin el modelo.

Las preguntas laterales conservan estado, borrador, referencia y correcciones
pendientes; «Continuar solicitud» vuelve al resumen o al dato faltante. Las
correcciones continúan requiriendo aceptación y confirmación final independientes.
Un mensaje del modelo que indique `human_handoff` no autoriza la derivación si el texto
del cliente no contiene una petición explícita. «Sí» aislado no autoriza atención
humana; la aceptación se realiza mediante el botón. No se habilitan Search/Maps.
Los documentos son hechos aprobados, no instrucciones para cambiar estas reglas.
No se afirma que este enfoque elimine todos los errores de clasificación.

Las pruebas usan datos y proveedores sintéticos; las de PostgreSQL solo una base
vacía y desechable mediante `TEST_DATABASE_URL`. Cubren recuperación, duplicados,
confirmación, pausas, cierre, canal verificado y resultados inciertos, sin enviar
mensajes reales ni guardar credenciales de producción.

## Derivación al WhatsApp del asesor (Beta 1.05)

En Admin → Asistente se configura el nombre, teléfono internacional, nombre de
plantilla aprobada e idioma. El aviso está apagado por defecto. La configuración
usa `GET/PATCH /assistant/preferences/advisor` con Admin, Bearer JWT y CSRF en la
mutación; no modifica el contrato ni el valor del interruptor de lenguaje natural.
La plantilla debe tener tres parámetros de cuerpo posicionales: código de consulta,
teléfono del cliente y resumen. El asesor debe haber aceptado recibir estos avisos.
No se asume una ventana WhatsApp abierta: el API envía siempre la plantilla configurada.
Ejemplo de cuerpo a aprobar en Meta:

> Nueva consulta {{1}}. Cliente: {{2}}. Resumen: {{3}}. Contacta al cliente desde tu WhatsApp.

El asesor responde directamente desde su propio WhatsApp; sus mensajes al cliente
no se sincronizan con Admin. No se ha implementado una bandeja de atención humana.

Una conversación por número contiene varias `conversation_interactions`, cada una
con código único y mensajes asociados. Se conserva un snapshot al derivar. La
migración `0006` es aditiva: los mensajes históricos conservan interacción nullable;
no reabre solicitudes confirmadas ni reanuda pausas previas.

Al solicitar asesor, una transacción cierra la interacción como `referred`, guarda
el aviso con destino y plantilla congelados, prepara la confirmación y abre otra
interacción. El nuevo estado queda en menú, con borrador vacío y código diferente.
El worker entrega, en orden: aviso al asesor, confirmación al cliente y bienvenida
original con imagen, botones y nuevo código. Los tres trabajos se guardan antes de
confirmar el webhook. Los botones que referencian mensajes de una interacción
anterior no vuelven a derivarla. Los reintentos del mismo evento son idempotentes.

Si falta configuración o Meta rechaza el aviso, el cliente recibe un texto honesto
que indica que su consulta se registró pero el aviso no pudo confirmarse, seguido
de la nueva bienvenida. Admin muestra pendientes, aceptados, entregados, leídos,
fallidos y resultados inciertos. HTTP 200 de Meta significa aceptación, no entrega.
Los callbacks de estado verificados actualizan los avisos sin retroceder de leído.
Un envío de asesor incierto no se repite automáticamente ni bloquea la nueva
interacción; un intento interrumpido pasa a incierto tras 60 segundos. Los envíos
inciertos al cliente siguen requiriendo revisión operativa y pausan ese chat.
No se promete un tiempo fijo de respuesta ni se intenta reenviar cotizaciones.

## Aclaración de fechas parciales (Beta 1.07)

En la captura de fecha, «Diciembre 12» o «12 de diciembre» conserva día y mes
en el estado de la interacción y pregunta únicamente el año. Una respuesta como
«2027» completa la fecha sin inferir el año actual. La fecha se valida contra el
calendario y la fecha local de Costa Rica antes de avanzar; tampoco se aceptan
fechas pasadas. El borrador, la referencia y los demás datos se conservan, incluso
si se consulta el menú antes de continuar. Los mensajes con varios datos siguen
usando la extracción validada. La revisión final del cliente continúa siendo
obligatoria. Esta aclaración literal también funciona en el fallback sin IA.

## Confirmación contextual del servicio (Beta 1.09)

Cuando el siguiente dato faltante es el servicio y se pregunta por parrillada,
«Sí», «Si», «Claro» y afirmaciones equivalentes completan `service_type=parrilla`
y muestran la revisión, conservando los otros datos. Esta aceptación literal
funciona también sin IA. Una negativa ofrece opciones sin inventar otro servicio,
sin perder el borrador y sin derivar automáticamente a un asesor. Las respuestas
con más datos siguen pasando por extracción y revisión de correcciones.
Un «sí» aislado en otros pasos no completa campos ni acepta cambios o el envío
final: la confirmación final continúa requiriendo el botón «Confirmar datos».

## Nueva interacción después de confirmar (Beta 1.10)

Confirmar datos cierra la solicitud y conserva su código, snapshot e historial.
Si el cliente escribe otro texto, el servicio abre una interacción independiente
con código nuevo y envía la misma bienvenida del modo guiado y del modo natural.
La apertura no llama a Gemini ni modifica la solicitud confirmada. Las solicitudes
anteriores al registro de interacciones se archivan antes del reinicio.

Los botones antiguos no reabren solicitudes. Los duplicados del webhook no crean
otras interacciones, y una conversación pausada por atención humana o por un envío
incierto conserva la pausa. Los mensajes descartados antes de esta corrección no
se reproducen: el siguiente texto nuevo inicia la interacción.


## RAG con PostgreSQL y Gemini (Beta 1.12)

Migración `0007`: `knowledge_documents` conserva catálogo validado, versión, hash,
tenant, fuente, perfil de embeddings y publicación activa; `knowledge_chunks` guarda
los textos aprobados y vectores `vector(768)`. La migración crea la extensión si falta;
el downgrade conserva la extensión porque puede ser compartida. Requiere permisos de
instalación de extensión al migrar, nunca al atender mensajes. CI usa PostgreSQL16 con
pgvector y todas las pruebas SQL se ejecutan contra bases vacías y desechables.

Configuración del **API** (no Admin):

```dotenv
RAG_ENABLED=false
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_LOCATION=us-central1
RAG_MIN_SIMILARITY=0.35
```

Publicar primero el catálogo mediante el [procedimiento de carga](../knowledge/README.md)
y después activar `RAG_ENABLED=true`. Generación y extracción conservan el modelo
`GEMINI_MODEL` actual y `GOOGLE_CLOUD_LOCATION=global`. Los embeddings usan un cliente
regional separado con la misma identidad de servicio. No se crea una API key.

Una pregunta de menú, cobertura o preparación genera un embedding de consulta, busca
hasta tres fragmentos con distancia coseno y filtra por tenant, fuente, versión activa,
tema y perfil del modelo. Para este catálogo pequeño se usa búsqueda exacta, sin HNSW.
La similitud mínima es un umbral inicial del piloto, no una garantía de corrección;
debe medirse al ampliar el corpus.

Gemini recibe pregunta y evidencia como datos, sin herramientas. Devuelve únicamente
IDs de hechos suficientes para responder. Python valida que pertenezcan al resultado
y envía sus textos aprobados; no acepta prosa libre ni citas inventadas. Sin evidencia
suficiente se ofrece un asesor, sin pausar ni borrar el borrador. Precios, disponibilidad,
alergias y políticas conservan sus respuestas restrictivas y no usan esta recuperación.
Ante errores externos o catálogo aún no publicado se usa el respaldo validado del wheel.

No se ingieren conversaciones, teléfonos, credenciales, notas locales ni documentos
arbitrarios. La pregunta se envía a Google para consulta pero su vector no se guarda.
Cada versión se publica en una sola transacción después de obtener todos los embeddings.
No se hace ingesta ni se generan embeddings de documentos al iniciar la aplicación.
El endpoint de consulta `GET /assistant/knowledge` exige JWT Admin; el dashboard consume
solo este contrato HTTP y nunca importa modelos ni repositorios del módulo.

Fuentes de integración: [embeddings Google](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/text-embeddings-api)
y [pgvector para SQLAlchemy](https://github.com/pgvector/pgvector-python).

## Telemetría Gemini (Beta 1.13)

Admin → Asistente → Telemetría Gemini (`/dashboard/assistant/telemetry`) consulta
`GET /assistant/telemetry` con JWT Admin. Ofrece períodos de 24 horas, 7 y 30 días,
filtros por operación, agregados por modelo, evolución horaria/diaria y eventos
paginados de 50 en 50. La consulta no llama a Google. Sales no tiene acceso.

La migración `0008` agrega `gemini_telemetry`, con índice por tenant y fecha. Registra
extracción, embeddings de catálogo/consulta y selección de evidencia. Conserva
latencia monotónica, estado, región/modelo, motivo de finalización, clase de error,
código HTTP y los contadores que Google entregue: entrada, salida, razonamiento,
caché, herramientas, total y caracteres facturables de embeddings. Los campos
omitidos por Google permanecen nulos; no se convierten en cero ni se calculan totales
sumando caché otra vez. Los errores que devuelven uso también conservan ese consumo.

Los resultados de extracción y RAG son eventos internos separados: validación,
falta de evidencia, referencias inválidas y respaldo del catálogo. No aumentan el
contador de llamadas a Google. Una traza UUID agrupa los pasos de una consulta,
sin usar teléfono, mensaje, conversación o identidad del cliente. El tiempo del
recorrido RAG excluye la extracción inicial y la entrega de WhatsApp. p50/p95 son
percentiles reales calculados en PostgreSQL sobre los eventos del período.

La instrumentación empieza con esta versión: no reconstruye el consumo anterior.
Tampoco consulta facturación o cuota restante de Google; el panel lo indica y enlaza
a Cloud Billing para los importes reales. No estima dólares ni representa un límite
de gasto. Las métricas corresponden a este API y a cargas ejecutadas con su CLI;
no incluyen pruebas externas hechas directamente en Cloud Studio u otras aplicaciones.

No persiste prompts, respuestas, errores crudos, credenciales ni IDs de clientes.
El registro usa una transacción propia con límites de sentencia/bloqueo y falla sin
interrumpir al bot. Si falla, incrementa un contador en memoria visible en el panel
(desde el inicio del proceso); por eso el historial no es un libro de facturación.
La retención todavía no elimina registros automáticamente. Hay que medir crecimiento
y definir archivado antes de ampliar el volumen operativo.

Referencias de los campos de uso: [respuesta GenerateContent de Google](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse)
y tipos `GenerateContentResponseUsageMetadata`, `EmbedContentMetadata` y
`ContentEmbeddingStatistics` del SDK instalado.


### Acceso técnico desde Beta 1.14

El conocimiento publicado y la telemetría se consultan en Admin → RAG, exclusivamente
con Dev. Dev incluye los permisos Admin; Admin sin Dev conserva la configuración de
modo y asesor. Las rutas API canónicas son `/rag/knowledge` y `/rag/telemetry`.
Los enlaces anteriores de este documento describen la publicación inicial; sus
alias técnicos también requieren Dev a partir de la migración `0009`.
