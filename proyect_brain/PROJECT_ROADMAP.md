# Plataforma de Gestión Comercial para Servicios de Catering

## Documento de referencia del proyecto

**Versión:** 1.0

**Fecha:** 20 de octubre de 2026

**Estado:** Definición inicial del producto

**Carpeta de trabajo:** `proyect_brain`

**Decisiones actualizadas (1 de noviembre de 2026):** consultar [TECH_STACK_MVP.md](TECH_STACK_MVP.md). Registra el stack confirmado (Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Jinja2 y HTMX), dashboard privado con CRUD de cuentas, atención humana desde el dashboard y cotizaciones PDF con precios manuales, aprobación y envío separados. Estas decisiones prevalecen sobre las propuestas iniciales de este documento, incluida la separación del frontend y el alcance de propuestas PDF.

**Alcance de lanzamiento confirmado:** roles Admin y Sales; seguimiento al día siguiente mediante recordatorio interno para Daniel, sin mensaje automático al cliente. Google Calendar se pospone hasta después del lanzamiento; sus tareas y criterios de cierre descritos abajo no son requisitos de la primera entrega.

---

## 1. Resumen ejecutivo

La empresa necesita una plataforma para convertir las conversaciones de WhatsApp en oportunidades comerciales organizadas. El sistema debe ayudar a captar leads, recopilar la información necesaria para preparar propuestas de catering, dar seguimiento a cada oportunidad e integrar las fechas y recordatorios con Google Calendar.

La primera etapa se implementará **sin inteligencia artificial**. El bot utilizará flujos guiados, menús, botones y preguntas predefinidas. Esta decisión permite validar el proceso comercial, reducir el costo inicial y recopilar conversaciones reales antes de incorporar un modelo de lenguaje.

La arquitectura se preparará desde el comienzo para agregar IA en una segunda etapa sin reconstruir el backend, la base de datos ni el panel comercial.

---

## 2. Visión del producto

Crear una herramienta que permita a la empresa atender más solicitudes de catering, perder menos oportunidades y preparar propuestas con información completa y ordenada.

El sistema deberá conectar:

```text
Cliente por WhatsApp
        ↓
Bot de captura de información
        ↓
Lead estructurado
        ↓
Panel comercial
        ↓
Propuesta y seguimiento
        ↓
Google Calendar y notificaciones
```

---

## 3. Problema que se quiere resolver

Las solicitudes de catering pueden llegar en mensajes incompletos, en diferentes horarios y desde distintos contactos. Esto puede provocar:

- Información dispersa en conversaciones.
- Preguntas repetitivas para el cliente.
- Leads sin seguimiento.
- Dificultad para saber qué oportunidades están listas para una propuesta.
- Pérdida de fechas o tareas importantes.
- Tiempo excesivo para preparar propuestas.

La plataforma centralizará la información y establecerá un proceso comercial común.

---

## 4. Objetivos de negocio

### Objetivos iniciales

- Capturar todas las solicitudes recibidas por WhatsApp.
- Estandarizar la información de cada evento.
- Reducir el tiempo de respuesta inicial.
- Facilitar el trabajo del equipo comercial.
- Crear recordatorios y seguimientos confiables.
- Reducir la cantidad de oportunidades olvidadas.
- Preparar una base de datos histórica de clientes y eventos.

### Objetivos posteriores

- Permitir conversaciones en lenguaje natural.
- Automatizar la extracción de datos de mensajes libres.
- Asistir en la preparación de propuestas.
- Recomendar servicios o menús según el tipo de evento.
- Automatizar seguimientos basados en el estado del lead.

---

## 5. Alcance de la primera etapa sin IA

### Incluido en el MVP

#### WhatsApp

- Recepción de mensajes.
- Menú inicial de opciones.
- Botones o respuestas guiadas.
- Preguntas secuenciales.
- Confirmación de la información capturada.
- Derivación a un asesor.
- Mensajes de confirmación al cliente.

#### Captura de leads

El sistema debe guardar como mínimo:

- Nombre del contacto.
- Número de WhatsApp.
- Tipo de evento.
- Fecha del evento.
- Ubicación.
- Número aproximado de invitados.
- Tipo de servicio o menú.
- Presupuesto aproximado, si el cliente lo comparte.
- Requerimientos adicionales.
- Notas internas.
- Fuente del lead.
- Estado comercial.

#### Panel comercial

- Listado de leads.
- Búsqueda y filtros.
- Vista del detalle del lead.
- Historial de conversación.
- Actualización del estado.
- Asignación a un responsable.
- Notas internas.
- Tareas y próximos seguimientos.

#### Google Calendar

- Creación de recordatorios internos.
- Registro de fechas de eventos.
- Registro de tareas de seguimiento.
- Consulta preliminar de fechas, sujeto a aprobación del equipo.

#### Notificaciones

- Aviso al equipo cuando ingresa un lead.
- Confirmación de recepción al cliente.
- Aviso de datos faltantes.
- Recordatorio interno de seguimiento.
- Mensaje de propuesta lista, cuando corresponda.

### No incluido inicialmente

- Conversación abierta con IA.
- Cálculo automático de precios.
- Confirmación automática de disponibilidad definitiva.
- Generación avanzada de propuestas en PDF.
- Pagos en línea.
- Portal público para clientes.
- Integración con múltiples canales adicionales.

---

## 6. Flujo de atención de la primera etapa

### Flujo principal

1. El cliente escribe al número de WhatsApp.
2. El bot muestra las opciones disponibles.
3. El cliente selecciona “Solicitar cotización”.
4. El bot solicita los datos del evento.
5. El cliente responde utilizando botones o mensajes cortos.
6. El bot muestra un resumen de la solicitud.
7. El cliente confirma o corrige los datos.
8. El sistema crea el lead en PostgreSQL.
9. El equipo comercial recibe una notificación.
10. Se asigna el lead a un responsable.
11. Se crea una tarea de seguimiento.
12. El asesor revisa la fecha, disponibilidad, menú y condiciones.
13. El equipo prepara y envía la propuesta.
14. El lead avanza hasta ganado o perdido.

### Opciones iniciales del bot

- Solicitar una cotización.
- Ver servicios.
- Consultar una solicitud existente.
- Hablar con un asesor.

### Manejo de mensajes fuera del flujo

Cuando el sistema no pueda clasificar una respuesta, debe evitar improvisar y ofrecer una salida segura:

> No logré identificar la opción. Puede seleccionar una de las alternativas disponibles o escribir ASESOR para comunicarse con nuestro equipo.

La palabra o acción `ASESOR` debe activar la derivación a una persona.

---

## 7. Ejemplo de conversación guiada

**Cliente:** Hola

**Bot:** ¡Hola! Gracias por contactar a nuestra empresa de catering. ¿Qué desea hacer?

**Opciones:** Solicitar cotización | Ver servicios | Hablar con un asesor

**Cliente:** Solicitar cotización

**Bot:** ¿Qué tipo de evento está organizando?

**Opciones:** Boda | Corporativo | Cumpleaños | Reunión familiar | Otro

**Cliente:** Evento corporativo

**Bot:** ¿Para qué fecha necesita el servicio?

**Cliente:** 15 de diciembre

**Bot:** ¿En qué lugar se realizará?

**Cliente:** Zona 10

**Bot:** ¿Para cuántas personas?

**Cliente:** Aproximadamente 80

**Bot:** ¿Qué servicio le interesa?

**Opciones:** Buffet | Parrillada | Estaciones de comida | Menú personalizado

**Cliente:** Parrillada

**Bot:** Resumen: evento corporativo, 15 de diciembre, zona 10, 80 personas y servicio de parrillada. ¿Desea enviar esta solicitud?

**Opciones:** Confirmar solicitud | Corregir datos | Hablar con un asesor

**Bot:** Gracias. Recibimos su solicitud. Nuestro equipo revisará la información y se comunicará con usted por este mismo número.

---

## 8. Estados del lead

| Estado | Descripción |
|---|---|
| Nuevo | Solicitud recién recibida. |
| En calificación | Faltan datos o el equipo está revisando la solicitud. |
| Calificado | Hay información suficiente para analizar la oportunidad. |
| Propuesta en preparación | El equipo está construyendo la oferta. |
| Propuesta enviada | La propuesta fue enviada al cliente. |
| Seguimiento | Se espera una respuesta o decisión del cliente. |
| Ganado | El cliente confirmó el servicio. |
| Perdido | La oportunidad no avanzó y se registra el motivo. |
| Archivado | Registro cerrado que se conserva para consulta histórica. |

---

## 9. Arquitectura técnica propuesta

```text
Meta WhatsApp Business Platform
            ↓
        Webhook HTTPS
            ↓
        Backend FastAPI
            ├── Módulo de conversaciones
            ├── Módulo de leads
            ├── Módulo de clientes
            ├── Módulo de tareas
            ├── Módulo de propuestas
            ├── Integración Google Calendar
            ├── Servicio de notificaciones
            └── Cola de trabajos
            ↓
        PostgreSQL
            ↓
        Panel web comercial
```

### Backend

- FastAPI.
- SQLAlchemy.
- Alembic para migraciones.
- Pydantic para validación.
- PostgreSQL.
- Autenticación y autorización por roles.
- Configuración por variables de entorno.
- Pruebas automatizadas.
- Logs y health checks.

### Frontend

- Aplicación web separada del backend.
- Panel de leads.
- Vista de conversaciones.
- Filtros y estados.
- Gestión de tareas.
- Preparación para permisos por usuario.

### Infraestructura

- Docker para desarrollo consistente.
- Despliegue compatible con Railway u otro proveedor equivalente.
- Base de datos PostgreSQL administrada.
- Variables secretas separadas por entorno.
- Backups y monitoreo básico.

---

## 10. Entidades principales de datos

### Lead

- `id`
- `status`
- `source`
- `assigned_user_id`
- `contact_id`
- `event_type`
- `event_date`
- `location`
- `guest_count`
- `service_type`
- `budget`
- `requirements`
- `internal_notes`
- `created_at`
- `updated_at`

### Contacto

- `id`
- `name`
- `phone_number`
- `email`
- `company`
- `created_at`
- `updated_at`

### Conversación

- `id`
- `contact_id`
- `channel`
- `external_thread_id`
- `status`
- `created_at`
- `updated_at`

### Mensaje

- `id`
- `conversation_id`
- `direction`
- `external_message_id`
- `message_type`
- `content`
- `raw_payload`
- `sent_at`
- `delivery_status`

### Tarea

- `id`
- `lead_id`
- `assigned_user_id`
- `task_type`
- `due_at`
- `status`
- `notes`

### Evento de calendario

- `id`
- `lead_id`
- `external_calendar_id`
- `event_type`
- `start_at`
- `end_at`
- `status`

---

## 11. Integraciones

### WhatsApp

La recomendación inicial es evaluar primero Meta WhatsApp Business Platform directamente. Proveedores como Twilio, 360dialog o Vonage pueden ser alternativas si simplifican la activación, la operación o el soporte requerido.

Requisitos técnicos:

- Número de WhatsApp Business.
- Cuenta empresarial y acceso a la plataforma elegida.
- Webhook HTTPS.
- Verificación de firma o token.
- Idempotencia para no procesar dos veces el mismo mensaje.
- Registro del identificador externo del mensaje.
- Manejo de reintentos.
- Plantillas aprobadas cuando aplique.

### Google Calendar

El backend será el responsable de consultar o crear eventos. El bot no escribirá directamente en Calendar. Las acciones estarán sujetas a reglas y permisos del sistema.

Funciones iniciales:

- Crear recordatorio de seguimiento.
- Crear evento interno relacionado con una oportunidad.
- Consultar conflictos o disponibilidad preliminar.

### Notificaciones

Las notificaciones deben ejecutarse mediante tareas asíncronas para que un problema externo no bloquee la respuesta del bot.

---

## 12. Segunda etapa con LLM

La IA se agregará después de validar el flujo guiado.

### Capacidades esperadas

- Entender mensajes escritos libremente.
- Extraer fecha, ubicación, invitados, servicio y presupuesto.
- Detectar intención.
- Identificar datos faltantes.
- Hacer preguntas naturales.
- Resumir la solicitud.
- Detectar casos que necesitan un asesor.
- Responder preguntas frecuentes usando información aprobada.

### Ejemplo de extracción

Mensaje del cliente:

> Necesito comida para 80 personas el 15 de diciembre en zona 10, algo tipo parrillada.

Resultado estructurado esperado:

```json
{
  "intencion": "solicitar_cotizacion",
  "tipo_evento": null,
  "fecha": "2026-12-15",
  "cantidad_invitados": 80,
  "ubicacion": "Zona 10",
  "tipo_menu": "parrillada",
  "presupuesto": null,
  "datos_faltantes": ["tipo_evento", "presupuesto"]
}
```

### Principio de seguridad

El LLM interpretará y propondrá acciones, pero el backend validará y ejecutará las operaciones. La IA no debe:

- Confirmar precios sin una regla o aprobación.
- Confirmar disponibilidad definitiva sin autorización.
- Crear eventos externos sin validación.
- Modificar un lead sin registrar el cambio.
- Inventar políticas, menús o condiciones.

La implementación futura puede usar Structured Outputs para exigir un esquema consistente y function calling para conectar funciones controladas del backend.

Funciones potenciales:

```text
crear_lead(datos)
actualizar_lead(id, cambios)
consultar_disponibilidad(fecha)
crear_recordatorio(lead_id, fecha)
derivar_a_asesor(lead_id)
buscar_servicio(nombre)
```

---

## 13. Proveedores y costos

### Proveedores probables

| Servicio | Proveedor inicial recomendado | Alternativas |
|---|---|---|
| WhatsApp | Meta WhatsApp Business Platform | Twilio, 360dialog, Vonage |
| LLM futuro | OpenAI API | Anthropic, Google Gemini |
| Backend y base de datos | Railway o proveedor equivalente | Render, AWS, Azure, DigitalOcean |
| Calendario | Google Calendar API | Microsoft Graph Calendar |
| Dominio y correo | Proveedor elegido por la empresa | Según necesidades del cliente |

### Costos de la primera etapa

La primera etapa no tendrá consumo de LLM. Los costos principales serán:

- Uso de WhatsApp y posibles cargos del proveedor.
- Infraestructura del backend.
- PostgreSQL.
- Dominio y certificados, si aplican.
- Google Cloud para habilitar la API de Calendar.
- Desarrollo, pruebas, soporte y mantenimiento.

### Costos de la segunda etapa

Al agregar IA aparecerá un costo variable por uso del modelo. El precio dependerá del volumen de mensajes, tamaño de las conversaciones y modelo seleccionado. Se debe establecer un límite de consumo y alertas antes de activar la IA en producción.

No se recomienda entrenar un modelo propio al inicio. Primero se deben probar instrucciones, datos estructurados, reglas y herramientas controladas.

---

## 14. Fases de implementación

### Fase 0 Descubrimiento

- Revisar el proceso comercial actual.
- Definir tipos de eventos.
- Definir catálogo de servicios.
- Definir preguntas obligatorias.
- Definir estados y responsables.
- Aprobar mensajes del bot.
- Confirmar proveedor de WhatsApp.
- Confirmar calendario y permisos.

### Fase 1 MVP sin IA

- Configurar proyecto y ambientes.
- Crear base de datos y migraciones.
- Implementar webhook de WhatsApp.
- Implementar flujo guiado.
- Crear leads y conversaciones.
- Crear panel comercial básico.
- Integrar notificaciones.
- Integrar tareas y Calendar.
- Crear pruebas.

### Fase 2 Optimización

- Revisar métricas.
- Mejorar preguntas.
- Agregar plantillas de propuesta.
- Agregar roles y permisos.
- Mejorar filtros y reportes.
- Documentar operación.

### Fase 3 Lenguaje natural

- Integrar proveedor LLM.
- Crear esquema de extracción.
- Agregar clasificación de intención.
- Agregar function calling controlado.
- Agregar fallback y derivación humana.
- Probar con conversaciones reales anonimizadas.
- Activar gradualmente por grupos o tipos de lead.

### Fase 4 Automatización avanzada

- Propuestas asistidas.
- Seguimientos automáticos.
- Recomendaciones de servicios.
- Métricas comerciales avanzadas.
- Integración con otros canales si el negocio lo requiere.

---

## 15. Indicadores de éxito

- Leads capturados por WhatsApp.
- Porcentaje de solicitudes con información completa.
- Tiempo promedio de respuesta inicial.
- Tiempo desde el primer contacto hasta la calificación.
- Tiempo desde la calificación hasta el envío de propuesta.
- Porcentaje de leads con seguimiento registrado.
- Seguimientos vencidos.
- Conversión de lead a propuesta.
- Conversión de propuesta a venta.
- Motivos de pérdida.

---

## 16. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambios en reglas o precios de WhatsApp | Confirmar el proveedor y revisar condiciones antes de producción. |
| Mensajes duplicados | Idempotencia usando el identificador externo del mensaje. |
| Pérdida de datos | Validación, transacciones, backups y auditoría. |
| Bot bloqueado por una respuesta inesperada | Opción clara para hablar con un asesor. |
| Fechas confirmadas incorrectamente | Calendar como apoyo; confirmación final por el equipo. |
| Costos inesperados de IA | Límites, alertas y activación gradual. |
| Dependencia excesiva del proveedor | Encapsular las integraciones detrás de servicios propios. |
| Resistencia del equipo comercial | Probar el flujo con usuarios reales y ajustar antes del lanzamiento. |

---

## 17. Decisiones pendientes

Antes de comenzar el desarrollo se deben confirmar:

- Nombre comercial del sistema.
- Proveedor de WhatsApp.
- Número que se utilizará.
- Tipos de eventos que se atenderán inicialmente.
- Catálogo de servicios y menús.
- Campos obligatorios del lead.
- Estados comerciales definitivos.
- Usuarios y roles del equipo.
- Calendario o calendarios que se integrarán.
- Quién puede confirmar disponibilidad.
- Quién puede enviar propuestas.
- Formato de propuesta.
- Política de seguimiento.
- Presupuesto y cronograma del MVP.

---

## 18. Próximo paso

Realizar un taller de levantamiento de requisitos con el equipo comercial. El resultado debe ser un documento aprobado con:

1. Flujo completo de WhatsApp.
2. Lista de preguntas y respuestas.
3. Campos del lead.
4. Estados y responsables.
5. Reglas de derivación a asesor.
6. Reglas de Calendar.
7. Mensajes aprobados.
8. Alcance final del MVP.

Este archivo debe mantenerse actualizado como la fuente de verdad del proyecto. Toda decisión importante de producto, arquitectura o integración debe agregarse aquí o registrarse en un documento de decisión relacionado.

---

## 20. Checklist de implementación por etapas

Este checklist será utilizado para controlar el avance del proyecto. Una etapa se considera completa cuando sus tareas principales están marcadas y sus criterios de cierre fueron verificados.

### Fase 0 Descubrimiento y definición

- [ ] Confirmar el nombre final del producto.
- [ ] Confirmar el número de WhatsApp que se utilizará.
- [ ] Confirmar el responsable comercial del proyecto.
- [ ] Documentar el proceso actual desde el primer contacto hasta el cierre.
- [ ] Definir los tipos de eventos iniciales.
- [ ] Definir el catálogo de servicios y menús.
- [ ] Definir opciones de BBQ gourmet, parrillada, buffet y menú personalizado.
- [ ] Definir si se ofrecerá alquiler de equipos en el MVP.
- [ ] Definir preguntas obligatorias para una solicitud de cotización.
- [ ] Definir información opcional del cliente.
- [ ] Definir estados del lead.
- [ ] Definir responsables por estado.
- [ ] Definir reglas de derivación a un asesor.
- [ ] Aprobar mensajes iniciales del bot.
- [ ] Aprobar mensajes de confirmación.
- [ ] Aprobar mensajes de error y fallback.
- [ ] Confirmar el calendario o calendarios de Google que se integrarán.
- [ ] Definir quién puede consultar fechas.
- [ ] Definir quién puede confirmar disponibilidad.
- [ ] Definir formato de la propuesta comercial.
- [ ] Definir métricas iniciales.
- [ ] Aprobar alcance y presupuesto del MVP.

**Criterio de cierre:** existe un documento aprobado con el flujo de WhatsApp, campos del lead, catálogo inicial, estados, responsables, mensajes y reglas de operación.

### Fase 1 Preparación técnica

- [ ] Crear repositorio del proyecto.
- [ ] Crear estructura `backend` y `frontend`.
- [ ] Definir ambientes local, staging y producción.
- [ ] Configurar variables de entorno.
- [ ] Crear proyecto de PostgreSQL.
- [ ] Configurar SQLAlchemy.
- [ ] Configurar Alembic.
- [ ] Crear configuración central de FastAPI.
- [ ] Crear endpoint de health check.
- [ ] Configurar logging básico.
- [ ] Configurar autenticación inicial.
- [ ] Definir roles de usuario.
- [ ] Preparar Docker Compose para desarrollo.
- [ ] Definir estrategia de backups.
- [ ] Crear pipeline básico de pruebas.
- [ ] Documentar comandos de instalación y ejecución.

**Criterio de cierre:** el backend inicia correctamente, se conecta a PostgreSQL, ejecuta migraciones y tiene ambientes separados con configuración segura.

### Fase 2 WhatsApp y flujo guiado

- [ ] Crear o configurar la cuenta de WhatsApp Business.
- [ ] Confirmar proveedor: Meta, Twilio, 360dialog u otro.
- [ ] Configurar webhook HTTPS.
- [ ] Implementar verificación del webhook.
- [ ] Validar mensajes entrantes.
- [ ] Guardar el identificador externo del mensaje.
- [ ] Implementar idempotencia.
- [ ] Implementar manejo de reintentos.
- [ ] Implementar menú inicial.
- [ ] Implementar opción de solicitar cotización.
- [ ] Implementar opción de ver servicios.
- [ ] Implementar opción de hablar con un asesor.
- [ ] Implementar captura de nombre.
- [ ] Implementar captura de teléfono.
- [ ] Implementar captura de tipo de evento.
- [ ] Implementar captura de fecha.
- [ ] Implementar captura de ubicación.
- [ ] Implementar captura de invitados.
- [ ] Implementar captura de servicio o menú.
- [ ] Implementar captura de presupuesto opcional.
- [ ] Implementar captura de necesidades adicionales.
- [ ] Implementar resumen de la solicitud.
- [ ] Implementar confirmación o corrección de datos.
- [ ] Implementar fallback para respuestas no reconocidas.
- [ ] Implementar derivación a asesor.
- [ ] Probar mensajes repetidos.
- [ ] Probar respuestas incompletas.
- [ ] Probar abandono y reanudación de conversación.

**Criterio de cierre:** un usuario puede iniciar una conversación, completar una solicitud, confirmar los datos y ser derivado a un asesor sin intervención técnica.

### Fase 3 Leads y base de datos

- [ ] Crear tabla de contactos.
- [ ] Crear tabla de leads.
- [ ] Crear tabla de conversaciones.
- [ ] Crear tabla de mensajes.
- [ ] Crear tabla de tareas.
- [ ] Crear tabla de eventos de calendario.
- [ ] Definir relaciones y claves foráneas.
- [ ] Definir índices para búsquedas frecuentes.
- [ ] Implementar creación de lead.
- [ ] Implementar actualización de lead.
- [ ] Implementar deduplicación por teléfono.
- [ ] Implementar historial de cambios.
- [ ] Implementar estados del lead.
- [ ] Implementar asignación de responsable.
- [ ] Implementar notas internas.
- [ ] Implementar tareas de seguimiento.
- [ ] Crear migraciones iniciales.
- [ ] Crear datos de prueba.
- [ ] Crear pruebas de servicios y repositorios.

**Criterio de cierre:** cada conversación confirmada produce un lead persistente, consultable y trazable en PostgreSQL.

### Fase 4 Panel comercial

- [ ] Crear inicio de sesión.
- [ ] Crear vista de leads.
- [ ] Crear filtros por estado.
- [ ] Crear filtros por fecha.
- [ ] Crear filtros por responsable.
- [ ] Crear búsqueda por nombre o teléfono.
- [ ] Crear vista de detalle del lead.
- [ ] Mostrar historial de conversación.
- [ ] Mostrar datos del evento.
- [ ] Permitir cambiar estado.
- [ ] Permitir asignar responsable.
- [ ] Permitir agregar notas.
- [ ] Permitir crear tareas.
- [ ] Mostrar próximos seguimientos.
- [ ] Mostrar leads vencidos.
- [ ] Crear permisos básicos por rol.
- [ ] Probar uso en móvil y escritorio.
- [ ] Validar usabilidad con el equipo comercial.

**Criterio de cierre:** el equipo comercial puede trabajar un lead desde el panel sin necesitar acceso directo a la base de datos.

### Fase 5 Google Calendar y notificaciones

- [ ] Crear proyecto de Google Cloud.
- [ ] Habilitar Google Calendar API.
- [ ] Configurar OAuth o cuenta de servicio según el caso.
- [ ] Definir permisos del calendario.
- [ ] Implementar creación de recordatorios.
- [ ] Implementar creación de tareas de seguimiento.
- [ ] Implementar eventos internos relacionados con leads.
- [ ] Implementar consulta preliminar de disponibilidad.
- [ ] Evitar confirmar disponibilidad automáticamente.
- [ ] Implementar notificación de nuevo lead al equipo.
- [ ] Implementar confirmación de recepción al cliente.
- [ ] Implementar notificación de datos faltantes.
- [ ] Implementar manejo de errores de Calendar.
- [ ] Implementar reintentos de notificaciones.
- [ ] Registrar las referencias externas de Calendar.

**Criterio de cierre:** un lead puede generar una tarea o recordatorio en Google Calendar y el equipo recibe las notificaciones esperadas.

### Fase 6 Pruebas y lanzamiento del MVP

- [ ] Crear pruebas unitarias del backend.
- [ ] Crear pruebas de integración del webhook.
- [ ] Probar flujo completo de WhatsApp.
- [ ] Probar duplicación de mensajes.
- [ ] Probar fallos de proveedores externos.
- [ ] Probar permisos de usuarios.
- [ ] Probar backups y restauración.
- [ ] Revisar logs y errores.
- [ ] Revisar seguridad de variables secretas.
- [ ] Probar en ambiente staging.
- [ ] Ejecutar pruebas con usuarios internos.
- [ ] Ejecutar piloto con un grupo pequeño de prospectos.
- [ ] Recopilar comentarios del equipo.
- [ ] Corregir defectos críticos.
- [ ] Preparar guía de uso.
- [ ] Capacitar al equipo comercial.
- [ ] Activar producción.
- [ ] Confirmar monitoreo post-lanzamiento.

**Criterio de cierre:** el MVP está en producción, el equipo fue capacitado y existe un procedimiento para atender errores o derivar conversaciones a una persona.

### Fase 7 Optimización comercial

- [ ] Revisar el porcentaje de leads completos.
- [ ] Revisar tiempos de respuesta.
- [ ] Revisar seguimientos vencidos.
- [ ] Revisar conversión de lead a propuesta.
- [ ] Revisar conversión de propuesta a venta.
- [ ] Revisar motivos de pérdida.
- [ ] Identificar preguntas repetitivas.
- [ ] Mejorar el orden de las preguntas.
- [ ] Mejorar mensajes y textos del bot.
- [ ] Crear plantillas de propuestas.
- [ ] Agregar reportes comerciales.
- [ ] Agregar permisos más detallados.
- [ ] Documentar procesos operativos.
- [ ] Priorizar mejoras para el siguiente ciclo.

**Criterio de cierre:** existe un informe de resultados del MVP y una lista priorizada de mejoras basada en datos reales.

### Fase 8 Integración de lenguaje natural

- [ ] Revisar conversaciones reales y anonimizadas.
- [ ] Identificar intenciones frecuentes.
- [ ] Definir esquema estructurado de extracción.
- [ ] Definir campos con alta confianza y baja confianza.
- [ ] Seleccionar proveedor LLM.
- [ ] Configurar límites de consumo.
- [ ] Crear prompt y reglas del asistente.
- [ ] Implementar extracción de fecha, lugar e invitados.
- [ ] Implementar clasificación de intención.
- [ ] Implementar preguntas adaptativas.
- [ ] Implementar respuestas basadas en contenido aprobado.
- [ ] Implementar function calling controlado.
- [ ] Implementar consulta segura de Calendar.
- [ ] Implementar derivación por baja confianza.
- [ ] Implementar registro del uso y costo del LLM.
- [ ] Crear pruebas con conversaciones representativas.
- [ ] Activar la IA inicialmente para un porcentaje limitado de leads.
- [ ] Comparar resultados contra el flujo guiado.
- [ ] Ajustar reglas y prompts.
- [ ] Expandir gradualmente el uso en producción.

**Criterio de cierre:** el bot entiende mensajes libres con un nivel aceptable de precisión, mantiene validaciones del backend y deriva correctamente los casos que requieren intervención humana.

### Fase 9 Automatización avanzada

- [ ] Generar borradores de propuestas.
- [ ] Permitir revisión y aprobación interna.
- [ ] Automatizar recordatorios de seguimiento.
- [ ] Recomendar servicios o menús aprobados.
- [ ] Agregar respuestas a preguntas frecuentes.
- [ ] Agregar métricas de rendimiento del asistente.
- [ ] Agregar control de presupuesto de IA.
- [ ] Revisar calidad de respuestas periódicamente.
- [ ] Documentar cambios del comportamiento del bot.
- [ ] Crear proceso de revisión humana y mejora continua.

**Criterio de cierre:** el sistema automatiza tareas repetitivas sin quitar al equipo comercial el control sobre precios, disponibilidad, propuestas y compromisos con el cliente.

---

## 21. Referencia visual y posicionamiento comercial

Se revisó el sitio `parrillasensucasa.com` como referencia de la identidad y los servicios del negocio. La comunicación principal observada se centra en:

- BBQ gourmet y parrillada creativa.
- Preparación de alimentos en el lugar del evento.
- Servicio personalizado.
- Menús adaptados al evento.
- Alquiler de equipos.
- Atención de bodas, eventos corporativos, reuniones y celebraciones.
- Uso de carnes premium, guarniciones, panes artesanales y diferentes técnicas de cocción.

Se extrajeron materiales visuales para la propuesta comercial en:

```text
proyect_brain/assets/logo-parrillas.png
proyect_brain/assets/portada-parrillada.png
proyect_brain/assets/parrillada-evento.jpg
proyect_brain/assets/servicio-parrilla.png
proyect_brain/assets/carnes.png
```

Antes de una entrega pública o comercial definitiva, se debe confirmar que la empresa autoriza el uso de estas imágenes y del logotipo en los documentos y materiales del nuevo sistema.
