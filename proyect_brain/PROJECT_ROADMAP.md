# Plataforma de Gestión Comercial para Servicios de Catering

## Documento de referencia del proyecto

**Versión:** 1.2

**Fecha:** 20 de octubre de 2026

**Última actualización:** 7 de noviembre de 2026 (America/Costa_Rica)

**Estado:** Base técnica, cuentas, recepción idempotente y panel de integraciones desplegados; verificación de callback Meta resuelta; prueba con número de WhatsApp y flujo comercial pendientes

**Carpeta de trabajo:** `proyect_brain`

**Decisiones actualizadas (1 de noviembre de 2026):** consultar [TECH_STACK_MVP.md](TECH_STACK_MVP.md). Stack confirmado: Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic y Admin con Jinja2; HTMX se incorporará cuando aporte interacción útil. Admin y API viven en servicios Railway separados; Admin llama al API por HTTP privado con JWT y solo el API accede a PostgreSQL. El MVP incluye CRUD de cuentas, atención humana desde el dashboard y cotizaciones PDF con precios manuales, aprobación y envío separados. Estas decisiones prevalecen sobre las propuestas iniciales de este documento.

**Alcance de lanzamiento confirmado:** roles Admin y Sales; seguimiento al día siguiente mediante recordatorio interno para Daniel, sin mensaje automático al cliente. Google Calendar se pospone hasta después del lanzamiento; sus tareas y criterios de cierre descritos abajo no son requisitos de la primera entrega.

---

## 1. Resumen ejecutivo

La empresa necesita una plataforma para convertir las conversaciones de WhatsApp en oportunidades comerciales organizadas. El sistema debe ayudar a captar leads, recopilar información para propuestas de catering y registrar seguimientos internos para Daniel. Google Calendar se integrará después del lanzamiento.

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
Recordatorio interno para Daniel
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

#### Google Calendar (posterior al lanzamiento)

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
        Webhook HTTPS (verificación disponible; recepción pendiente de credenciales)
            ↓
        API FastAPI
            ├── Módulo de conversaciones
            ├── Módulo de leads
            ├── Módulo de clientes
            ├── Módulo de tareas
            ├── Módulo de propuestas
            ├── Integración Google Calendar (posterior)
            ├── Servicio de notificaciones
            └── Cola de trabajos
            ↓
        PostgreSQL (privado)

Navegador → Admin Jinja2 (web, HTTPS)
                    ↓ HTTP privado + Bearer JWT
                API FastAPI
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

- Servicio Admin separado del API, en el mismo repositorio e imagen Docker con factories distintas.
- Jinja2 para las páginas; cliente HTTP hacia el API, sin SQL ni clave de firma JWT en Admin.
- Panel de leads.
- Vista de conversaciones.
- Filtros y estados.
- Gestión de tareas.
- Preparación para permisos por usuario.

### Infraestructura

- Docker para desarrollo consistente.
- Railway: `web` (Admin público), `api` (red privada y entrada pública autenticada para webhooks) y `Postgres` (privado).
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

Se utiliza Meta WhatsApp Business Platform directamente. El callback HTTPS y su verificación GET están desplegados; el usuario confirmó que la validación en Meta ya funciona. La recepción firmada e idempotente está implementada, pero sigue deshabilitada hasta completar App Secret, Business Account ID y Phone Number ID en el API. El siguiente paso es configurar el número de prueba de Meta y un destinatario verificado.

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
- Google Cloud para Calendar se evaluará después del lanzamiento.
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
- Implementar recordatorios internos para Daniel; Calendar queda para después del lanzamiento.
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

Antes de completar el flujo comercial se deben confirmar los siguientes puntos. Stack, roles Admin/Sales, Daniel como responsable, precios manuales, aprobación y envío separados, recordatorio interno y presupuesto de hosting de USD 35/mes ya están acordados en [TECH_STACK_MVP.md](TECH_STACK_MVP.md).

- Datos legales completos del operador; el correo público confirmado es info@parrillasensucasa.com.
- Acceso técnico a Meta y número que se utilizará, sin guardar credenciales en este documento.
- Tipos de eventos que se atenderán inicialmente.
- Catálogo de servicios y menús.
- Validación final del flujo y textos a partir de `Conversación BOT WATS.docx`; fecha, invitados y ubicación son las preguntas principales acordadas.
- Estados comerciales definitivos.
- Cuentas concretas del equipo; los roles ya están definidos.
- Calendario y permisos, después del lanzamiento.
- Quién puede confirmar disponibilidad.
- Plantilla visual y contenido final de la propuesta PDF; Daniel aprueba y pulsa Enviar.
- Hora exacta del recordatorio interno del día siguiente, política de retención y almacenamiento de PDFs.
- Backups, restauración y consumo real de los tres servicios Railway frente al presupuesto acordado.

---

## 18. Próximo paso

Retomar desde el estado desplegado del 7 de noviembre de 2026. Acceso, separación Admin/API, webhook seguro e Integraciones ya están implementados:

1. Seleccionar el número de prueba de Meta y verificar el teléfono del destinatario. Completar en el API `WHATSAPP_APP_SECRET`, `WHATSAPP_BUSINESS_ACCOUNT_ID` y `WHATSAPP_PHONE_NUMBER_ID`; el verify token ya está configurado. Para el diagnóstico de conexión también faltan `WHATSAPP_ACCESS_TOKEN` y `WHATSAPP_GRAPH_API_VERSION`. No copiar secretos a este documento ni a fixtures.
2. Probar la recepción firmada con eventos sintéticos y el número de prueba de Meta, incluida la suscripción al campo `messages`. Verificar persistencia, duplicados y errores; la validación del callback por sí sola no demuestra recepción de mensajes reales.
3. Implementar el procesador persistente del inbox hacia conversaciones/leads, con recuperación tras fallos, y el adaptador de envío. Los eventos guardados con `processed_at = NULL` todavía no crean conversaciones ni respuestas.
4. Implementar el flujo guiado: fecha, invitados y ubicación; preguntas complementarias según la referencia, confirmación de datos y derivación humana.
5. Construir el inbox de Daniel en Admin mediante llamadas al API, con pausa/reanudación explícita del bot y envío manual.
6. Continuar con borrador PDF, precios manuales, aprobación y envío separados, y recordatorio interno al día siguiente del envío confirmado.

En paralelo quedan pendientes staging, backups/restauración y control de costos. Autodeploy de `main` con Wait for CI ya se comprobó de extremo a extremo en `api` y `web`. Mantener las pruebas con el número de Meta separadas del tráfico de clientes hasta completar procesamiento persistente, operación humana y validación del flujo.

Este archivo debe mantenerse actualizado como la fuente de verdad del proyecto. Toda decisión importante de producto, arquitectura o integración debe agregarse aquí o registrarse en un documento de decisión relacionado.

---

## 19. Cierre de jornada — 1 de noviembre de 2026

Registro histórico del primer despliegue. El estado vigente y la entrega del 7 de noviembre están en las secciones 18 y 22.

### Objetivos completados

- [x] Inicializar el repositorio modular y sincronizarlo con [lkccomander/parrilladasC](https://github.com/lkccomander/parrilladasC), rama `main`.
- [x] Documentar arquitectura, stack, operación de cuentas y despliegue; registrar las convenciones de mantenimiento en `AGENTS.md`.
- [x] Crear modelos iniciales y migraciones `0001`/`0002`: cuentas, sesiones, intentos de acceso, leads, conversaciones, mensajes, cotizaciones y recordatorios. Las tablas comerciales todavía no constituyen flujos operativos completos.
- [x] Implementar login/logout, bootstrap privado del primer Admin y recuperación de contraseña mediante comando privado; sin contraseña predeterminada.
- [x] Implementar CRUD de cuentas con roles Admin/Sales, desactivación/reactivación, validación, Argon2id, límites de intentos y revocación de sesiones.
- [x] Aplicar el diseño acordado al login y Admin, con imágenes de marca y fuentes locales.
- [x] Publicar privacidad y términos en español e inglés, con botón de idioma en los encabezados. Datos legales adicionales del operador siguen pendientes.
- [x] Separar Admin y API en servicios desplegables: `parrilladas.admin:create_app` y `parrilladas.main:create_app`. Admin usa el cliente HTTP `AdminApiClient`; no accede directamente a la base.
- [x] Implementar JWT de acceso de hasta 15 minutos, refresh tokens rotativos y sesión absoluta de ocho horas. Validar firma, issuer, audience y sesión/cuenta actual en el API; mantener cookies HttpOnly y protección CSRF en formularios y mutaciones del API.
- [x] Desplegar en Railway `web` (Admin), `api` y `Postgres`, con red privada y health checks. Solo el API recibe `DATABASE_URL` y `JWT_SECRET` y ejecuta migraciones; se verificó su ausencia en el contenedor Admin.
- [x] Corregir permisos de GitHub y habilitar autodeploy desde `main` en `api` y `web`, con Wait for CI activo en ambos. Verificar los triggers guardados en Railway y conservar `checkSuites: true` en `.railway/railway.ts`.
- [x] Actualizar Docker y Compose para ejecutar ambos servicios independientemente, y validar la configuración Compose.
- [x] Validar 43 pruebas con PostgreSQL desechable, Ruff, formato, dependencias, instalación limpia y empaquetado. GitHub Actions pasó para el commit `6848f52`.
- [x] Verificar en navegador local dos procesos separados y comprobar en producción readiness privado, JWT, CSRF, rutas protegidas y páginas legales bilingües.
- [x] Corregir dependencias faltantes de la `.venv` de Windows y completar la configuración local ignorada por Git; verificar imports y carga de configuración del API con `/docs` habilitado.
- [x] Refrescar GitNexus al commit `6848f52`: 90 archivos, 640 nodos, 1.137 relaciones y 29 flujos. Confirmar que reconoce el cliente HTTP de Admin y la validación JWT del API. Esta actualización documental es posterior a ese índice.

### Punto de entrega

Admin: [web-production-528a1.up.railway.app](https://web-production-528a1.up.railway.app/login). API interno: `http://api.railway.internal:8080`, sin dominio público ni `/docs` en producción. Documentación local: `http://localhost:8001/docs`.

Código y convenciones sincronizados hasta `6848f52`. Ese despliegue se realizó explícitamente desde GitHub. Después del cierre se corrigieron los permisos y se habilitaron los triggers automáticos de `main` con Wait for CI en ambos servicios; configuración verificada, pendiente observar el próximo push con cambios de aplicación. La infraestructura y el acceso están operativos; WhatsApp, inbox comercial, PDF y recordatorios siguen pendientes. Consultar [plan de implementación](../docs/implementation-plan.md), [arquitectura](../docs/architecture.md) y [Railway](../docs/railway.md).

### CI/CD habilitado

Flujo configurado: **push a `main` → GitHub Actions → Railway espera CI → despliegue automático de `api` y `web`**. Cada servicio se despliega por separado; las migraciones siguen ejecutándose únicamente en el API.

Ambos servicios observan `/backend/**`, `/Dockerfile` y `/.dockerignore`. Los cambios exclusivos de documentación no redespliegan la aplicación; los cambios en `.railway/` requieren plan y aplicación explícita de infraestructura.

- [x] Confirmar rama `main`, repositorio `lkccomander/parrilladasC` y `checkSuites: true` en ambos triggers mediante la API de Railway.
- [x] Observar pushes con cambios de aplicación, CI exitoso y despliegues saludables de ambos servicios; comprobado el 7 de noviembre con `03faaba` y `7fe2b37`.

---

## 20. Checklist de implementación por etapas

Este checklist será utilizado para controlar el avance del proyecto. Una etapa se considera completa cuando sus tareas principales están marcadas y sus criterios de cierre fueron verificados.

### Fase 0 Descubrimiento y definición

- [ ] Confirmar el nombre final del producto.
- [ ] Confirmar el número de WhatsApp que se utilizará.
- [x] Confirmar a Daniel como responsable comercial del proyecto.
- [ ] Documentar el proceso actual desde el primer contacto hasta el cierre.
- [ ] Definir los tipos de eventos iniciales.
- [ ] Definir el catálogo de servicios y menús.
- [ ] Definir opciones de BBQ gourmet, parrillada, buffet y menú personalizado.
- [ ] Definir si se ofrecerá alquiler de equipos en el MVP.
- [x] Definir preguntas obligatorias para una solicitud de cotización.
- [x] Definir información opcional del cliente.
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
- [x] Aprobar alcance y presupuesto del MVP.

**Criterio de cierre:** existe un documento aprobado con el flujo de WhatsApp, campos del lead, catálogo inicial, estados, responsables, mensajes y reglas de operación.

### Fase 1 Preparación técnica

- [x] Crear repositorio del proyecto.
- [x] Crear módulos Python y separar servicios Admin/API en el mismo paquete; no se requiere carpeta `frontend`.
- [x] Configurar ambientes local y producción con servicios Admin/API independientes.
- [ ] Preparar staging con secretos y base independientes.
- [x] Configurar variables de entorno.
- [x] Crear proyecto de PostgreSQL.
- [x] Configurar SQLAlchemy.
- [x] Configurar Alembic.
- [x] Crear configuración central de FastAPI.
- [x] Crear endpoint de health check.
- [x] Configurar logging básico.
- [x] Configurar autenticación inicial.
- [x] Definir roles de usuario.
- [x] Preparar Docker Compose para desarrollo.
- [ ] Definir estrategia de backups.
- [x] Crear pipeline básico de pruebas.
- [x] Habilitar despliegues automáticos de Admin y API desde `main`, esperando CI exitoso.
- [x] Documentar comandos de instalación y ejecución.

**Criterio de cierre:** Admin y API arrancan por separado; solo el API conecta a PostgreSQL y ejecuta migraciones. Local y producción están configurados; staging y estrategia de backups continúan pendientes, por lo que la fase no está cerrada por completo.

### Fase 2 WhatsApp y flujo guiado

- [ ] Crear o configurar la cuenta de WhatsApp Business.
- [x] Confirmar proveedor: Meta WhatsApp Business Platform directo.
- [x] Configurar webhook HTTPS público en el servicio API.
- [x] Implementar verificación GET con token independiente de la recepción; validación en Meta confirmada por el usuario.
- [x] Implementar validación de firma HMAC SHA-256 sobre el body original, payload, cuenta y número permitidos.
- [x] Guardar el identificador externo de mensajes y estados en el inbox persistente.
- [x] Implementar idempotencia por evento, incluso con concurrencia y cambios de agrupación.
- [x] Responder 200 después del commit y 503 ante fallos de persistencia para permitir reintentos de Meta.
- [ ] Configurar App Secret e IDs del número de prueba y comprobar recepción real.
- [ ] Configurar token de acceso y versión de Graph API; comprobar conectividad real desde Integraciones.
- [ ] Implementar procesamiento persistente y recuperación de eventos pendientes del inbox.
- [ ] Implementar envíos persistentes con reintentos.
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
- [x] Probar eventos repetidos y lotes concurrentes con PostgreSQL desechable.
- [ ] Probar respuestas incompletas.
- [ ] Probar abandono y reanudación de conversación.

**Criterio de cierre:** un usuario puede iniciar una conversación, completar una solicitud, confirmar los datos y ser derivado a un asesor sin intervención técnica.

### Fase 3 Leads y base de datos

- [x] Modelar inicialmente datos de contacto dentro de `leads`; tabla independiente pendiente si el comportamiento la requiere.
- [x] Crear tabla de leads.
- [x] Crear tabla de conversaciones.
- [x] Crear tabla de mensajes.
- [x] Crear `whatsapp_inbox_events` y migración `0003`, con clave única, payload privado y estado de procesamiento pendiente.
- [x] Crear tabla `reminders` para recordatorios internos; programación y ejecución pendientes.
- [ ] Crear tabla de eventos de calendario.
- [x] Definir relaciones y claves foráneas.
- [x] Crear índices iniciales de leads, conversaciones y mensajes; ajustar según las consultas comerciales futuras.
- [ ] Implementar creación de lead.
- [ ] Implementar actualización de lead.
- [ ] Implementar deduplicación por teléfono.
- [ ] Implementar historial de cambios.
- [ ] Implementar estados del lead.
- [ ] Implementar asignación de responsable.
- [ ] Implementar notas internas.
- [ ] Implementar tareas de seguimiento.
- [x] Crear migraciones iniciales.
- [ ] Crear datos de prueba.
- [x] Probar servicios y persistencia de cuentas con PostgreSQL desechable.
- [ ] Agregar pruebas de servicios comerciales conforme se implementen.

**Criterio de cierre:** cada conversación confirmada produce un lead persistente, consultable y trazable en PostgreSQL.

### Fase 4 Panel comercial

- [x] Crear y estilizar el panel privado y el CRUD de cuentas.
- [x] Publicar privacidad y términos bilingües con selector de idioma.
- [x] Consumir el API desde Admin por HTTP privado con JWT.
- [x] Publicar la tarjeta Meta y WhatsApp y `/dashboard/integrations`, solo para Admin, con formulario CSRF.
- [x] Mostrar URL del callback y estado de configuración/verificación; comprobar acceso a cuenta y número mediante una consulta de lectura a Meta.
- [ ] Implementar inbox de Daniel y control explícito de pausa/reanudación del bot.
- [ ] Crear plantilla PDF y almacenamiento privado.
- [ ] Preparar borrador de cotización con precios introducidos manualmente por Daniel.
- [ ] Separar edición, aprobación y envío; exigir nueva aprobación tras cada cambio.
- [ ] Crear recordatorio interno para Daniel al día siguiente del envío confirmado, sin mensaje automático al cliente.
- [x] Crear inicio de sesión.
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
- [x] Crear permisos básicos por rol.
- [ ] Probar uso en móvil y escritorio.
- [ ] Validar usabilidad con el equipo comercial.

**Criterio de cierre:** el equipo comercial puede trabajar un lead desde el panel sin necesitar acceso directo a la base de datos.

### Fase 5 Google Calendar y notificaciones (Calendar posterior al lanzamiento)

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

**Criterio de cierre posterior al lanzamiento:** un lead puede generar una tarea o recordatorio en Google Calendar y el equipo recibe las notificaciones esperadas. Para el MVP basta implementar el recordatorio interno para Daniel; no requiere Google Calendar.

### Fase 6 Pruebas y lanzamiento del MVP

La base técnica ya está desplegada. Activar el MVP comercial requiere completar y probar WhatsApp, leads, cotizaciones, recordatorios y operación del equipo.

- [x] Crear pruebas unitarias del backend.
- [x] Crear pruebas de integración del webhook, transacciones, rollback e idempotencia con PostgreSQL desechable.
- [ ] Probar flujo completo de WhatsApp.
- [x] Probar duplicación y concurrencia de eventos con datos sintéticos.
- [x] Probar timeouts, límites, tokens rechazados y respuestas inválidas de Meta mediante transporte simulado; prueba real pendiente.
- [x] Probar permisos de usuarios.
- [ ] Probar backups y restauración.
- [ ] Revisar logs y errores.
- [x] Revisar seguridad de variables secretas.
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

Borradores con precios manuales, aprobación y recordatorios internos ya forman parte del alcance MVP de la fase 4; esta fase posterior amplía sus capacidades.

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

---

## 22. Entrega y punto de continuidad — 7 de noviembre de 2026

### Implementado y desplegado

- `03faaba`: recepción de webhooks y panel Admin de integraciones. Firma sobre bytes originales, límite de body de 1 MiB, validación de cuenta/número y mensajes de error sin secretos ni datos del cliente.
- Inbox PostgreSQL `whatsapp_inbox_events`, registrado en metadata y migración `0003`. Mensajes, estados y notificaciones de error se conservan de forma privada; deduplicación por clave estable, transacciones por lote y orden de escritura consistente.
- Panel **Meta y WhatsApp** en Inicio y navegación de Admin. Consulta de configuración y prueba manual de acceso a Meta/cuenta/número; tokens y secretos permanecen en el API. Roles Admin/Sales y CSRF comprobados en ambos servicios.
- Dominio público del API y `API_PUBLIC_BASE_URL` configurados en Railway. El enlace de Admin al API sigue usando red privada.
- `7fe2b37`: verificación de suscripción habilitada con solo `WHATSAPP_VERIFY_TOKEN`. Los POST siguen deshabilitados hasta completar App Secret e IDs. El mismo token se guardó en Railway; su valor no se registra aquí.
- Prueba pública: token correcto devuelve exactamente `hub.challenge` con 200, token incorrecto devuelve 403 y recepción incompleta devuelve 503. El usuario confirmó que la verificación en Meta funciona.

### Direcciones operativas

| Servicio | Dirección |
|---|---|
| Admin | `https://web-production-528a1.up.railway.app` |
| Integraciones | `https://web-production-528a1.up.railway.app/dashboard/integrations` |
| API público | `https://api-production-3c20d.up.railway.app` |
| Callback de Meta | `https://api-production-3c20d.up.railway.app/webhooks/whatsapp` |
| API privado para Admin | `http://api.railway.internal:8080` |

### Validación y alcance real

- 91 pruebas pasaron con PostgreSQL vacío y desechable, incluidas migraciones, permisos, CSRF, firmas, duplicados, concurrencia y rollback. Ruff, formato y `pip check` pasaron.
- GitHub Actions pasó para `7fe2b37`, incluida construcción del wheel. Railway terminó con API y Admin saludables tras esperar CI.
- La recepción real y el diagnóstico autenticado de Meta siguen pendientes de las credenciales e IDs indicados en la sección 18. Aún no hay procesamiento del inbox, leads operativos, bot guiado, inbox de atención humana, PDF ni recordatorios funcionales.
- El siguiente paso acordado es usar el número de prueba de Meta y un destinatario verificado. No se asignó un número de producción ni se enviaron mensajes a clientes desde Parrilladas.
- Google Calendar e IA siguen fuera del lanzamiento. Precios manuales, aprobación y envío separados, nueva aprobación tras editar y seguimiento interno para Daniel mantienen su alcance original.

Detalles de configuración y operación: [WhatsApp](../docs/whatsapp.md), [plan de implementación](../docs/implementation-plan.md) y [Railway](../docs/railway.md).
