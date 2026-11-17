# Implementación del MVP

## Base inicial

- [x] Git local y exclusiones para credenciales y artefactos.
- [x] Paquete Python con app factory y módulos de negocio.
- [x] Configuración por entorno y sesiones de DB por request.
- [x] Modelos y migración inicial.
- [x] Health checks y plantilla pública mínima.
- [x] Docker Compose y workflow CI con PostgreSQL efímero.
- [x] Pruebas de aprobación de cotización, aplicación y migraciones.

GitHub Actions ejecuta los checks en cada push. Los despliegues desde `main` usan servicios Admin y API separados. Solo el API ejecuta migraciones previas; ambos tienen health checks. Autodeploy de `main` está habilitado en Admin y API con Wait for CI; los watch paths limitan los despliegues a cambios de la aplicación.

## Acceso y cuentas

- [x] Bootstrap seguro del primer Admin mediante comando privado, sin contraseña por defecto.
- [x] Login/logout con JWT, refresh tokens rotativos, sesiones revocables y protección CSRF.
- [x] CRUD de cuentas para Admin; desactivación/reactivación conserva historial.
- [x] Permisos Admin/Sales, comprobados en backend.
- [x] Pruebas de autorización, contraseñas, throttling, concurrencia y desactivación.

Antes del primer ingreso en producción, el operador debe crear el Admin en una terminal privada. Instrucciones: [acceso y cuentas](accounts.md).

- [x] Separar Admin y API mediante HTTP privado; Admin sin credenciales de base ni clave JWT.

## Conversaciones y leads

- [x] Recepción Meta con verificación de suscripción, firma e inbox persistente idempotente.
- [x] Panel Admin de integraciones: configuración, webhook y diagnóstico de conectividad con Meta/WhatsApp.
- [x] Procesamiento persistente del inbox hacia conversaciones y envío Meta con control de intentos inciertos.
- [ ] Vincular solicitudes de conversación con leads y completar operación de atención humana.
- [ ] Preguntas guiadas: fecha, invitados y ubicación; completar datos relevantes del demo.
- [ ] Captura de leads y confirmación de datos.
- [x] Derivación al WhatsApp del asesor, configuración Admin e interacciones independientes.
- [x] Listado privado de interacciones en Atención y ventas para Admin/Sales, con búsqueda, estados y paginación.
- [ ] Inbox privado, mensajes y pausa/reanudación manual del bot.
- [ ] Envío manual desde dashboard con estado y errores visibles.

## Cotizaciones y tareas

- [ ] Plantilla PDF y almacenamiento privado.
- [ ] Borrador con datos del evento y precios introducidos por Daniel.
- [ ] Editar, aprobar y enviar como operaciones separadas.
- [ ] Ediciones invalidan aprobación y no permiten enviar versiones antiguas.
- [ ] Envíos persistentes con reintentos y protección contra duplicados.
- [ ] Recordatorio interno para Daniel al día siguiente del envío confirmado.

## Lanzamiento

- [x] Seleccionar Railway y desplegar aplicación/PostgreSQL con conexión privada.
- [ ] Configurar backups y comprobar consumo dentro del presupuesto.
- [ ] Staging, secretos independientes y prueba completa con Meta.
- [ ] Restauración de backup, permisos y recuperación de fallos.
- [ ] Piloto con Daniel y guía de operación.

## Lenguaje natural: piloto y preferencias

- [x] Contratos validados, gate apagado por defecto y preservación de datos confirmados.
- [x] Adaptador Vertex AI con ADC, salida JSON, límites y fallback ante fallos.
- [x] Comando sintético local y pruebas con proveedor simulado.
- [x] Cuenta de servicio dedicada en API Railway y llamada sintética verificada a
      Google Cloud; conexión habilitada para diagnóstico, bot todavía guiado.
- [x] Preferencia persistida de Admin/API con JWT, permisos, CSRF y migración `0005`;
      el modo efectivo combina la preferencia con los gates y runtime del API.
- [x] Canal Meta verificado del único tenant, aplicación del modo y recuperación durable.
- [x] Extracción Gemini, aclaración/confirmación explícita, correcciones y pausa.
- [x] Respuestas controladas desde el catálogo editable, límites de intención y fallback sin pausa.
- [ ] Recuperación vectorial, herramientas de revisión operativa de envíos inciertos y evaluación del piloto real.

Ver [piloto de extracción](assistant.md). La activación requiere gates del API y preferencia Admin. Google Calendar continúa fuera del alcance.
