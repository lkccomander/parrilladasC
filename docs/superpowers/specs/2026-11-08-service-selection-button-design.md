# Diseño: selección de servicio con botón

## Objetivo

Mejorar el paso de servicio del flujo guiado de cotización de Beta 1.00 para
que el cliente seleccione una opción clara desde WhatsApp, sin depender de que
escriba el nombre del servicio correctamente.

## Alcance aprobado

- Después de capturar la cantidad de invitados, el bot preguntará qué servicio
  le interesa al cliente.
- La respuesta mostrará un único botón interactivo: `Parrilla`.
- El identificador interno del botón será `service_parrilla` y el título visible
  será `Parrilla`.
- Al seleccionar el botón, se guardará `service_type = "parrilla"` y el flujo
  avanzará al resumen de la solicitud.
- Si el cliente escribe texto en lugar de seleccionar el botón, el bot repetirá
  la pregunta y mostrará nuevamente el botón.
- No se mostrarán todavía buffet, estaciones de comida ni menú personalizado.

## Arquitectura y datos

- La decisión seguirá siendo responsabilidad de `modules/conversations/flow.py`.
- `ConversationService` continuará traduciendo la respuesta interactiva de Meta
  a `ButtonReply` y persistiendo la actualización del flujo.
- El adaptador de WhatsApp enviará el botón usando el contrato existente de
  acciones salientes; no se añadirán reglas comerciales al router ni al
  adaptador externo.

## Manejo de errores

- Un botón desconocido o una respuesta de texto vacía no avanzará el flujo.
- La pregunta se repetirá sin sobrescribir `service_type`.
- Cada respuesta inválida consecutiva incrementará un contador de fallback de
  la conversación.
- Al llegar a tres respuestas inválidas consecutivas, el bot reconocerá que no
  pudo interpretar la opción, reiniciará el flujo desde el saludo inicial y
  restablecerá el contador.
- Una respuesta válida restablecerá el contador de respuestas inválidas.
- No se registrarán tokens, secretos ni contenido sensible adicional.

## Pruebas y aceptación

- La transición de `guest_count` mostrará la pregunta de servicio con el botón
  `Parrilla`.
- `ButtonReply("service_parrilla")` avanzará a `summary` y actualizará el
  servicio a `parrilla`.
- Un texto libre en `service_type` mantendrá el paso y volverá a mostrar el
  botón.
- Tres respuestas inválidas consecutivas reiniciarán el flujo y mostrarán el
  saludo inicial.
- Una respuesta válida después de un intento inválido permitirá continuar sin
  reiniciar la conversación.
- Los identificadores y títulos de botones conservarán el formato que ya usa
  el envío de WhatsApp.
- Las pruebas existentes del flujo inicial y de persistencia seguirán pasando.
