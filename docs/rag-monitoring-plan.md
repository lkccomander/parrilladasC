# Plan de implementación: RAG → Monitoreo

Estado: implementado en Beta 1.16; pendiente de despliegue posterior a CI.
Fecha: 21 de noviembre de 2026.
Especificación: `logs/rag-dashboard-implementation-spec.md`.

## Ubicación y permisos

Agregar «Monitoreo RAG» dentro de RAG, junto a Conocimiento y Telemetría Gemini.
Página Admin: `/dashboard/rag/monitoring`; API: `/rag/monitoring/*`.
Las páginas, parciales y endpoints requieren Dev; Admin sin Dev y Sales reciben
403. Se conserva JWT entre servicios y CSRF en toda mutación.

Prevalecen las decisiones actuales sobre dos instrucciones antiguas de la
especificación: RAG sigue exclusivo de Dev y no se apaga ni enciende lenguaje
natural. No cambia el flujo comercial ni la recuperación para mejorar métricas.

## Inspección confirmada en el repositorio

- `knowledge_documents`: tenant, fuente, versión, hash, modelo/región, publicación
  mediante `active` y catálogo JSON; timestamps heredados de `Record`.
- `knowledge_chunks`: documento, tema, texto aprobado y `vector(768)`. Tenant y
  versión se resuelven por el documento; no duplicarlos innecesariamente.
- No existen `published_at`, `indexed_at`, `valid_until` ni estado de aprobación
  separado. No presentar `created_at` como fecha de indexación verificada.
- Las migraciones no crean HNSW/IVFFlat: recuperación coseno exacta, filtro tenant,
  fuente, publicación, tema y perfil, umbral configurable, máximo tres resultados.
  Consultar los catálogos PostgreSQL para detectar el índice real en cada entorno.
- `gemini_telemetry` ya registra llamadas, tokens, errores, latencia y trazas por
  UUID. Reutilizarlo: no crear otro contador `llm_calls` que duplique eventos.
- `KnowledgeService.answer` conoce los fragmentos recuperados y seleccionados;
  allí se pueden observar IDs, puntuaciones y tiempos sin almacenar la pregunta.
- `Telemetry` ya persiste con transacciones independientes y fallo tolerado.
- `ConversationWorker` se compone en el lifespan del API. Los chequeos periódicos
  deben usar una tarea del API con límites y bloqueo entre réplicas, sin retrasar
  el procesamiento inbox/outbox ni depender de una pestaña abierta.
- Admin usa `AdminApiClient`, contratos y Jinja2; no tiene conexiones SQL.
- CI ya prueba migraciones con PostgreSQL/pgvector desechable y valida wheel.

## Adaptaciones que requieren confirmar

1. Conservar Dev y el estado actual de Gemini; usar búsqueda exacta sin nuevo ANN.
2. Registrar hashes HMAC de preguntas con secreto exclusivo del API, IDs,
   puntuaciones y tiempos. No habilitar almacenamiento de texto de clientes.
   Retención de trazas: 30 días, con purga acotada y programada.
3. Evaluaciones desde JSON versionado mantenido por el operador. No inventar los
   veinte casos ni ejecutar un juez LLM. Relevancia semántica queda «No medida».
   La ejecución con Gemini será explícita, con presupuesto/límites configurados.
4. Umbrales iniciales de la especificación configurables y visibles como
   provisionales. Precios por modelo y fecha de actualización configurables;
   sin tabla de precios o correlación de conversación, costo no medido.
5. No añadir caducidad funcional al recuperador en este trabajo observacional.
   Vigencia y retraso de indexación quedan no medidos donde faltan metadatos;
   detectar versiones inactivas recuperadas sí es posible. Añadir fechas
   verificables a futuras publicaciones no reconstruye datos históricos.

## Orden de implementación y commits

1. **Instrumentación y migración `0010`.** Crear `assistant/monitoring/` con
   contratos, modelos, repositorio y servicio de registro. Registrar modelos en
   `db/models.py`. Añadir `rag_query_traces` con tenant, traza compartida,
   hash HMAC, tiempos, configuración efectiva, IDs/rangos/puntuaciones usados y
   resultado. Ampliar telemetría existente solo donde falte información necesaria;
   no guardar mensajes, respuestas de clientes, secretos o errores crudos.
   Modificar `rag.py`, `telemetry.py` y `assistant/config.py` para observaciones
   tolerantes a fallos. No asociar automáticamente una ausencia de evidencia con
   una derivación: registrar la decisión real y distinguir fallback del catálogo.

2. **Métricas y consultas.** `monitoring/metrics.py`, `repository.py`, `service.py`
   y contratos. Agregados SQL por tenant y rango 24 h/7 d/30 d, percentiles,
   salud vectorial y catálogo de índices. Pruebas con valores calculados a mano.
   Separar Recall@5 de evaluaciones y recuperación online actual con k=3; nunca
   cambiar el límite productivo para llenar un indicador. Proxy determinista de
   fidelidad etiquetado como tal; no presentarlo como juicio semántico completo.

3. **Evaluación y migración `0011`.** Tablas `rag_eval_sets`, `rag_eval_cases`,
   `rag_eval_runs`, `rag_eval_case_results`; registro explícito en metadata.
   `monitoring/evaluation.py` y `monitoring/cli.py` para importar JSON curado y
   ejecutar trabajos persistidos con exclusión mutua, tiempos máximos y límites.
   Respuestas sintéticas de evaluación separadas de trazas online. ANN sweep
   solo si el catálogo confirma un índice ANN; con exacta, ocultarlo.

4. **API y pantalla.** `monitoring/router.py` con contratos Dev y tenant resuelto
   por el servidor, límites de paginación y consultas acotadas. Modificar
   `dashboard/client.py`, `dashboard/router.py` y `templates/rag.html`.
   Nuevas plantillas `templates/rag_monitoring/` con las nueve secciones de la
   especificación, parciales HTMX y SVG accesible, conservando el estilo actual.
   Detalle por traza con títulos/IDs y evidencia usada; sin texto del cliente.
   Estado vacío explícito y métricas desconocidas con valor nulo.

5. **Operación y migración `0012`.** `rag_alerts`, `rag_probe_runs` y
   `rag_index_checks`. Implementar reglas, deduplicación/resolución, purga y
   chequeos periódicos con locks y statement timeout. Probar aislamiento con
   segundo tenant sintético exclusivamente en DB desechable. Si no existen
   otros tenants reales, mostrar prueba operativa no realizada; no simular éxito.
   No notificaciones externas. Diagramas HNSW solo ilustrativos y solo con HNSW.

6. **Cierre.** Actualizar documentación, roadmap y versión con CI/CD GitHub.
   Revisar y probar cada migración en DB desechable. Antes de cerrar cada fase:
   Ruff, formato, suite completa, `pip check` y wheel. Pruebas de autorización
   Dev/Admin/Sales, CSRF, aislamiento, privacidad, estados vacíos, fallos de
   registro y regresión del bot. Verificación posterior al despliegue sin
   mensajes WhatsApp ni promociones de cuentas.

## Límites de interpretación

La retención no reconstruye trazas previas. «Exacta: recall del índice 100% por
definición» compara contra búsqueda exacta, no demuestra Recall@5 del negocio.
Tuplas muertas son una estimación operativa, no una medición física de bloat.
Las métricas de generación no medidas y los costos sin tarifa no se muestran
como cero. El mapa de conocimiento, SSE y nuevas dependencias pesadas quedan fuera.

La especificación exigía confirmar el plan antes de programar (regla 0.1).
La confirmación del operador fue recibida; las fases descritas ya están integradas
en el árbol de aplicación y la validación local pasó sin una base comercial.
