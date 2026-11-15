# Lenguaje natural: piloto y preferencias de Admin

El módulo `backend/src/parrilladas/modules/assistant/` valida intención y datos
del evento. El adaptador `integrations/vertex_ai/` usa el SDK Google Gen AI con
ADC local o una cuenta de servicio dedicada en Railway, un timeout de 30 segundos, un solo intento,
JSON estructurado, thinking mínimo y 512 tokens de salida por defecto. No utiliza
Search, Maps ni otras herramientas externas.

La extracción continúa como piloto local, sin conexión al webhook. El flag
`NATURAL_LANGUAGE_ENABLED` está desactivado por defecto y solo controla este
piloto, no el bot desplegado. RAG, la resolución de tenant desde Meta, la
recuperación durable y la integración con WhatsApp siguen pendientes.

## Preferencia persistida de Admin

La página **Admin → Asistente**, en `/dashboard/assistant`, permite guardar la
preferencia de lenguaje natural de Parrilladas. El API expone `GET` y `PATCH`
`/assistant/preferences`; ambos requieren una cuenta Admin activa y Bearer JWT.
El `PATCH` requiere también `X-CSRF-Token`. El formulario web valida CSRF y
solicitudes cross-site antes de reenviar la operación por HTTP al API.

La migración `0005` crea `assistant_preferences`, con clave `tenant_id`, valor
booleano apagado por defecto y fecha/actor de la última escritura. Antes de usar
la página en un entorno de despliegue, aplicar `alembic upgrade head` en la fase
de migración del API. No ejecutar migraciones desde el proceso web. Las pruebas
de migración usan únicamente `TEST_DATABASE_URL` vacío y desechable.

El tenant activo se fija en el servidor como `parrilladas`: las cuentas actuales
pertenecen a ese negocio y no existe administración multi-tenant. La mutación no
acepta `tenant_id`, y todas las consultas de preferencias aplican esa clave.
Antes de añadir otros negocios se necesita un resolver confiable y autorización
de pertenencia de cuentas; el modelo nunca determina el tenant.

La preferencia guardada y el modo operativo son conceptos distintos. Esta entrega
reporta siempre `active_mode=guided`, incluso con la preferencia encendida. La
página muestra «Activación pendiente» en ese caso. Guardar la preferencia no
realiza llamadas a Google, no reanuda conversaciones pausadas y no modifica sus
datos. El Admin no accede a PostgreSQL ni a las credenciales de Google Cloud.

El inicio del dashboard muestra dos tarjetas: **Modo guiado** y **Lenguaje natural**.
La etiqueta superior indica el modo efectivo consultado al API; encender la
preferencia solo cambia la tarjeta de lenguaje natural a «Activación pendiente».
Si no se puede consultar el estado, se muestra «Modo sin verificar», sin asumir
que algún modo está activo. Las tarjetas y la configuración son exclusivas de Admin.

## Ejecutar desde PowerShell

Con dependencias instaladas desde los locks y el paquete editable disponible:

```powershell
.\.venv\Scripts\python.exe -m parrilladas.modules.assistant.cli
```

Sin activación explícita muestra que está deshabilitado y no carga credenciales ni
realiza llamadas al proveedor. Para una prueba sintética con el proyecto piloto:

```powershell
gcloud auth application-default login
gcloud auth application-default set-quota-project parrilladas-ai-pilot
$env:APP_ENV = "development"
$env:GOOGLE_CLOUD_PROJECT = "parrilladas-ai-pilot"
$env:GOOGLE_CLOUD_LOCATION = "global"
$env:GEMINI_MODEL = "gemini-3.5-flash-lite"
$env:NATURAL_LANGUAGE_ENABLED = "true"
try {
    .\.venv\Scripts\python.exe -m parrilladas.modules.assistant.cli
} finally {
    $env:NATURAL_LANGUAGE_ENABLED = "false"
}
```

El comando envía una única solicitud sintética (20 personas, Alajuela y 20 de
diciembre del próximo año), verifica el resultado y no contacta a clientes ni
requiere PostgreSQL. La llamada genera consumo del modelo. El presupuesto de
alertas del piloto es USD 15/mes; las alertas no detienen el consumo. No copiar
credenciales ADC al repositorio ni al servicio Admin. La identidad de Railway
se configura por separado según [Railway](railway.md#conexión-con-google-cloud).

Para verificar exclusivamente la conexión, definir `VERTEX_CONNECTION_ENABLED=true`
y ejecutar el mismo comando con `--check-connection`. Esta comprobación permite
`APP_ENV=production` y no requiere activar `NATURAL_LANGUAGE_ENABLED`, que permanece
restringido al piloto local. El comando sin ese argumento conserva su gate original.
La comprobación usa datos sintéticos, no requiere PostgreSQL ni activa el webhook.
En producción se rechazan credenciales ADC personales.

Los IDs de modelo, proyecto y ubicación son configurables. Este modelo y `global`
se probaron desde el entorno local; no equivalen a una garantía de disponibilidad
en otros proyectos ni a residencia de datos en una región concreta.

## Contrato y límites

- `AssistantService.extract` devuelve un resultado estructurado; no envía mensajes,
  no persiste datos ni aprueba operaciones comerciales.
- Con el gate apagado o con `bot_paused=True` no llama al proveedor. La pausa tiene
  prioridad sobre el gate y el llamador debe obtenerla del estado persistido real.
- El resultado del modelo es una propuesta. Los datos confirmados son inmutables;
  los cambios se devuelven en `proposed_changes` para confirmación explícita.
- Fecha completa, invitados, ubicación y servicio componen los campos de revisión.
  No se exige presupuesto ni tipo de evento. El único servicio soportado en este
  piloto es `parrilla`, normalizado desde parrilla/parrillada.
- Las fechas necesitan año explícito y una cita literal del mensaje que incluya
  ese año. Fechas pasadas, sin evidencia o marcadas ambiguas requieren aclaración.
  Fechas relativas y formatos numéricos ambiguos quedan para una etapa posterior.
  La evidencia y la validación de tipos no demuestran por sí solas exactitud semántica.
- Los errores de autenticación, transporte y salida inválida producen fallback
  sin registrar prompts, credenciales o respuestas del proveedor. Las preguntas
  de negocio se derivan porque todavía no existe conocimiento RAG aprobado.
- Las pruebas usan proveedor simulado y datos sintéticos, sin consumo de modelos.

Antes de conectar el bot: resolver tenant desde Meta verificado; completar
recuperación persistente de inbox y envíos; integrar la preferencia guardada con
la selección efectiva del modo, aclaración/confirmación y atención humana;
evaluar ejemplos en español y aislamiento por tenant. Los precios siguen siendo
manuales y aprobación y envío permanecen separados.
