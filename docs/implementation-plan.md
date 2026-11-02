# Implementación del MVP

## Base inicial

- [x] Git local y exclusiones para credenciales y artefactos.
- [x] Paquete Python con app factory y módulos de negocio.
- [x] Configuración por entorno y sesiones de DB por request.
- [x] Modelos y migración inicial.
- [x] Health checks y plantilla pública mínima.
- [x] Docker Compose y workflow CI con PostgreSQL efímero.
- [x] Pruebas de aprobación de cotización, aplicación y migraciones.

GitHub Actions ejecuta los checks en cada push. Los despliegues desde `main` usan servicios Admin y API separados. Solo el API ejecuta migraciones previas; ambos tienen health checks. La activación de autodeploy sigue pendiente de la conexión GitHub del propietario.

## Acceso y cuentas

- [x] Bootstrap seguro del primer Admin mediante comando privado, sin contraseña por defecto.
- [x] Login/logout con JWT, refresh tokens rotativos, sesiones revocables y protección CSRF.
- [x] CRUD de cuentas para Admin; desactivación/reactivación conserva historial.
- [x] Permisos Admin/Sales, comprobados en backend.
- [x] Pruebas de autorización, contraseñas, throttling, concurrencia y desactivación.

Antes del primer ingreso en producción, el operador debe crear el Admin en una terminal privada. Instrucciones: [acceso y cuentas](accounts.md).

- [x] Separar Admin y API mediante HTTP privado; Admin sin credenciales de base ni clave JWT.

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

- [x] Seleccionar Railway y desplegar aplicación/PostgreSQL con conexión privada.
- [ ] Configurar backups y comprobar consumo dentro del presupuesto.
- [ ] Staging, secretos independientes y prueba completa con Meta.
- [ ] Restauración de backup, permisos y recuperación de fallos.
- [ ] Piloto con Daniel y guía de operación.

Google Calendar y conversación con IA quedan para después del lanzamiento.
