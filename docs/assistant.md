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

Una conversación nueva puede aportar fecha, invitados, ubicación y servicio en
un solo mensaje. El modelo propone datos; Python valida tipos, fecha completa con
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
La pausa requiere petición explícita de una persona o selección de «Hablar con asesor».
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
  ofrecer un asesor. La oferta no pausa; el cliente debe seleccionarla.
- «Quiero más información»: ofrecer menú, cobertura o solicitud.
- Fuera de tema: recordar el alcance y ofrecer continuar, sin borrar el borrador.
- Fallo/JSON inválido: conservar datos y ofrecer «Continuar sin IA». El modo literal
  valida fecha ISO completa, entero positivo, ubicación y servicio, sin el modelo.

Las preguntas laterales conservan estado, borrador, referencia y correcciones
pendientes; «Continuar solicitud» vuelve al resumen o al dato faltante. Las
correcciones continúan requiriendo aceptación y confirmación final independientes.
Un mensaje del modelo que indique `human_handoff` no autoriza la pausa si el texto
del cliente no contiene una petición explícita. «Sí» aislado no autoriza atención
humana; la aceptación se realiza mediante el botón. No se habilitan Search/Maps.
Los documentos son hechos aprobados, no instrucciones para cambiar estas reglas.
No se afirma que este enfoque elimine todos los errores de clasificación.

Las pruebas usan datos y proveedores sintéticos; las de PostgreSQL solo una base
vacía y desechable mediante `TEST_DATABASE_URL`. Cubren recuperación, duplicados,
confirmación, pausas, cierre, canal verificado y resultados inciertos, sin enviar
mensajes reales ni guardar credenciales de producción.
