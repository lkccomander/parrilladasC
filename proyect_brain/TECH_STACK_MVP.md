# Stack y alcance acordados para el MVP

Fecha: 1 de noviembre de 2026.

Este documento registra las decisiones confirmadas por el usuario y prevalece sobre las propuestas iniciales del roadmap cuando exista una diferencia.

## Restricciones

- Plazo objetivo: dos semanas de desarrollo.
- Presupuesto: USD 35 mensuales para hosting; no representa un presupuesto total de WhatsApp u otros servicios externos.
- Mantenimiento: a cargo del usuario.
- Volumen de consultas: todavía desconocido.

## Stack confirmado

| Área | Tecnología |
|---|---|
| Backend y bot | Python + FastAPI |
| Base de datos | PostgreSQL |
| Acceso a datos y migraciones | SQLAlchemy + Alembic |
| Dashboard privado | Jinja2 + HTMX |

Admin y API se despliegan en servicios separados, por indicación posterior del usuario. Admin conserva Jinja2/HTMX y llama al API por HTTP con JWT Bearer; solo el API accede a PostgreSQL y firma tokens. Hosting: Railway, con Admin público, API y PostgreSQL en red privada. Los webhooks de WhatsApp se implementarán en el API y requerirán exponer una entrada validada cuando corresponda. La librería de PDF y la implementación de trabajos persistentes quedan por seleccionar.

## Operación confirmada

- WhatsApp es el canal del cliente; la conexión con Meta ya existe, según el usuario.
- Primera versión con preguntas guiadas, sin IA.
- Daniel atiende y responde conversaciones desde el dashboard.
- La intervención de Daniel pausa las respuestas del bot en esa conversación; la reanudación debe ser explícita.
- El sistema prepara un borrador de cotización con los datos del evento.
- Daniel introduce los precios manualmente, revisa y edita el borrador.
- Se necesita una plantilla inicial de PDF; no existe una plantilla o catálogo de precios confirmado.
- Aprobar y enviar son acciones separadas. El sistema solo envía la cotización cuando Daniel pulsa Enviar.
- Una edición posterior a la aprobación debe requerir una nueva revisión antes del envío.
- Se requiere CRUD de cuentas de acceso al dashboard con dos roles confirmados: Admin (administra cuentas y todas las funciones) y Sales (gestiona conversaciones y cotizaciones). La política de eliminación queda por definir; el historial comercial debe conservar su trazabilidad.
- Al enviar la cotización, crear una tarea interna de seguimiento para Daniel al día siguiente, visible en el dashboard. Daniel realiza el contacto; el recordatorio no envía un mensaje automático al cliente.
- Google Calendar queda fuera del lanzamiento inicial y se integrará posteriormente.

Las reglas de pausa del bot y revisión tras editar son criterios de implementación propuestos para preservar el control humano acordado.

## Datos de la conversación de referencia

Fuente: `Conversación BOT WATS.docx`, casos 1 y 2 y preguntas frecuentes.

El documento pide explícitamente fecha del evento, cantidad de personas y ubicación. El primer caso también proporciona hora aproximada y tipo de servicio.

| Dato | Tratamiento inicial |
|---|---|
| Fecha del evento | Pregunta principal; confirmar fecha completa para evitar ambigüedad |
| Cantidad de personas | Pregunta principal |
| Ubicación del evento | Pregunta principal |
| Hora o franja horaria | Pregunta complementaria basada en el primer caso |
| Servicio o menú deseado | Confirmar la parrillada o solicitud específica |
| Nombre del contacto | Dato operativo propuesto para personalizar la atención |
| Número de WhatsApp | Obtener del mensaje entrante; no volver a preguntarlo |
| Niños y edades | Pregunta condicional para cotización cuando corresponda |
| Necesidades adicionales | Comentario opcional |

No hacer obligatorio el presupuesto ni el tipo de evento por el solo hecho de que aparecen en el roadmap: la conversación de referencia no los exige para iniciar una cotización.

Los datos ya confirmados por botones, formularios o Daniel deben reutilizarse. No se presupone extracción fiable de datos desde mensajes libres en una versión sin IA; el flujo debe permitir confirmarlos o derivar la conversación a Daniel.

## Referencias comerciales pendientes de validar para producción

El ejemplo menciona envío de PDF, enlace de Instagram, seguimiento al día siguiente, reserva con 50% por transferencia y saldo el día del evento. También incluye menús y condiciones para niños. Estos textos y precios son referencias del documento, no un catálogo vigente aprobado ni reglas de precios que el sistema deba aplicar automáticamente.

El seguimiento se registra como recordatorio interno para Daniel, sin envío automático de WhatsApp. Cuando Daniel contacte al cliente, el envío deberá respetar las reglas y plantillas de WhatsApp que correspondan.

## Decisiones restantes

- Política de cuentas definida: desactivación/reactivación, conservando historial; sin borrado físico.
- Plantilla visual y contenido final de la cotización.
- Seguimiento del presupuesto de Railway, incluyendo base de datos y backups.
- Retención y almacenamiento de PDFs.
- Librería de generación de PDF y trabajos persistentes para reintentos y recordatorios.
- Después del lanzamiento: definir alcance y calendario compartido para la integración de Google Calendar.
