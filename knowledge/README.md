# Conocimiento comercial de Parrilladas

Contenido inicial proporcionado por el negocio el 15 de noviembre de 2026.
Estos archivos preparan las fuentes para la futura ingesta RAG; todavía no se
importan a PostgreSQL ni generan embeddings automáticamente.

- [Menú legible](parrilladas/menu.md): presentación del menú y cobertura.
- [Menú estructurado](parrilladas/menu.json): fuente editable con categorías,
  platos y cobertura, identificada por `tenant_id=parrilladas`.

Para agregar un plato, añadir un elemento a `items` con un `id` único y estable,
`category_id` existente, `name`, `description` opcional y `active=true`.
Para ampliar categorías, añadirlas a `categories` y referenciarlas por su ID.
Desactivar un plato con `active=false` permite conservar su identificador.
Incrementar `content_version` al cambiar contenido y actualizar también el menú
legible. Esta estructura permite añadir platos sin cambiar código de Python.

Ejemplo de estructura para un plato nuevo (sustituir los textos de ejemplo antes
de incorporarlo al catálogo real):

```json
{
  "id": "identificador-del-plato",
  "category_id": "guarniciones",
  "name": "Nombre confirmado del plato",
  "description": null,
  "active": true
}
```

La cobertura en las siete provincias describe el área de servicio; no confirma
disponibilidad para una fecha. No se han definido precios, gramajes, paquetes,
mínimos de personas, costos de traslado ni restricciones alimentarias. No inferir
esos datos al responder con RAG. Los precios de las cotizaciones siguen siendo
manuales y la disponibilidad requiere confirmación operativa.

Las opciones generales de guarniciones dulces, saladas, frías o calientes no
equivalen a platos específicos ya registrados. Solo se ha nombrado ensalada verde.
Tampoco se han especificado variedades de panes, ingredientes, origen de las carnes
ni alérgenos. Al implementar ingesta, usar únicamente platos activos y guardar la
fuente, versión, tenant y configuración del embedding junto con los fragmentos.
