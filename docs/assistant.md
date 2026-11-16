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
Admin. La recuperación inicial selecciona hechos por tema, sin embeddings ni
consultas pgvector. Gemini clasifica la intención y el tema en un esquema cerrado;
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
