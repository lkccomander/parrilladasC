# Diseño: flujo guiado inicial de WhatsApp

## Objetivo

Implementar la primera experiencia demostrable del bot de Parrilladas en su Casa
para que un cliente pueda iniciar una solicitud de cotización desde WhatsApp.
La versión corresponde a Beta 1.00 y no utiliza IA, precios automáticos ni
confirmación automática de disponibilidad.

## Alcance de la primera versión

- Responder únicamente al primer mensaje de cada cliente con el saludo inicial.
- Mostrar la imagen de bienvenida de `assets/greeting-grill.png`.
- Presentar tres opciones:
  - `Solicitar cotización`, que inicia el flujo activo.
  - `Ver servicios`, que responde que estará disponible próximamente.
  - `Hablar con un asesor`, que responde que estará disponible próximamente y
    reconoce `ASESOR` como salida para atención humana.
- Persistir el estado de la conversación para no repetir el saludo después de
  reinicios o reintentos de Railway.
- Guardar el mensaje entrante antes de intentar enviar una respuesta.
- Ignorar duplicados y eventos de estado de entrega para el flujo conversacional.

## Flujo de solicitud de cotización

Después de seleccionar `Solicitar cotización`, el bot preguntará en este orden:

1. Tipo de evento.
2. Fecha del evento.
3. Lugar del evento.
4. Cantidad aproximada de invitados.
5. Servicio de interés: parrillada, buffet, estaciones de comida o menú personalizado.

El bot presentará un resumen con las respuestas y ofrecerá:

- `Confirmar solicitud`.
- `Corregir datos`.
- `Hablar con un asesor`.

Al confirmar, enviará una constancia de recepción y dejará la solicitud lista
para revisión del equipo comercial. La primera versión no calculará precios,
no confirmará disponibilidad y no enviará una propuesta automáticamente.

## Arquitectura y límites

- El webhook seguirá verificando la firma sobre el cuerpo original y validando
  la cuenta de negocio y el número telefónico antes de procesar eventos.
- El procesamiento se hará mediante servicios de conversaciones; el router
  solo leerá el webhook, validará y delegará.
- El adaptador de WhatsApp será responsable de enviar mensajes y medios a Meta.
- El envío se ejecutará después de persistir el evento entrante y deberá ser
  idempotente para no duplicar respuestas ante reintentos.
- Los tokens, secretos y contenido sensible no se escribirán en logs.
- La respuesta HTTP del webhook debe seguir siendo rápida y devolver `2xx` solo
  después de que el evento entrante quede persistido de forma segura.

## Manejo de errores

- Si falla el envío de la imagen, se enviará el saludo como texto.
- Si falla el envío de una respuesta, el fallo quedará registrado para revisión
  y no se marcará la conversación como completada.
- Mensajes que no correspondan al estado actual mostrarán una salida segura y
  ofrecerán reiniciar el flujo o escribir `ASESOR`.
- Los eventos duplicados no volverán a ejecutar preguntas ni respuestas.

## Criterios de aceptación

- Un primer mensaje produce un solo saludo con imagen y opciones.
- Un segundo mensaje del mismo cliente no repite el saludo.
- `Solicitar cotización` inicia las cinco preguntas en el orden definido.
- La confirmación devuelve el resumen y la constancia de recepción.
- `Ver servicios` y `Hablar con un asesor` devuelven respuestas de próxima
  disponibilidad sin fingir que esas funciones ya están implementadas.
- Un reintento del mismo evento no duplica la respuesta.
- Las pruebas cubren firma, idempotencia, estados del flujo y errores de Meta.
