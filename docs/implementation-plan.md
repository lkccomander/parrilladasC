# Implementación del MVP

## Base inicial

- [x] Git local y exclusiones para credenciales y artefactos.
- [x] Paquete Python con app factory y módulos de negocio.
- [x] Configuración por entorno y sesiones de DB por request.
- [x] Modelos y migración inicial.
- [x] Health checks y plantilla pública mínima.
- [x] Docker Compose y workflow CI con PostgreSQL efímero.
- [x] Pruebas de aprobación de cotización, aplicación y migraciones.

La existencia del workflow no implica que GitHub Actions ya se haya ejecutado; se activará al publicar.

## Siguiente: acceso y cuentas

- [ ] Bootstrap seguro del primer Admin.
- [ ] Login/logout con sesiones y protección CSRF.
- [ ] CRUD de cuentas para Admin; desactivación conserva historial.
- [ ] Permisos Admin/Sales, comprobados en backend.
- [ ] Pruebas de autorización, contraseñas y desactivación.

## Conversaciones y leads

- [ ] Adaptador Meta con firma, webhook e idempotencia.
- [ ] Preguntas guiadas: fecha, invitados y ubicación; completar datos relevantes del demo.
- [ ] Captura de leads y confirmación de datos.
- [ ] Inbox privado, mensajes y pausa/reanudación explícita del bot.
- [ ] Envío manual desde dashboard con estado y errores visibles.

## Cotizaciones y tareas

- [ ] Plantilla PDF y almacenamiento privado.
- [ ] Borrador con datos del evento y precios introducidos por Daniel.
- [ ] Editar, aprobar y enviar como operaciones separadas.
- [ ] Ediciones invalidan aprobación y no permiten enviar versiones antiguas.
- [ ] Envíos persistentes con reintentos y protección contra duplicados.
- [ ] Recordatorio interno para Daniel al día siguiente del envío confirmado.

## Lanzamiento

- [ ] Elegir hosting dentro del presupuesto y configurar backups.
- [ ] Staging, secretos independientes y prueba completa con Meta.
- [ ] Restauración de backup, permisos y recuperación de fallos.
- [ ] Piloto con Daniel y guía de operación.

Google Calendar y conversación con IA quedan para después del lanzamiento.
