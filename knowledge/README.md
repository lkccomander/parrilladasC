# Conocimiento comercial de Parrilladas

Contenido inicial proporcionado por el negocio el 15 de noviembre de 2026.
El JSON es la fuente aprobada del catálogo. Se empaqueta en el wheel y se publica
manualmente en PostgreSQL mediante `assistant.knowledge_cli ingest`. La carga genera
embeddings Google de 768 dimensiones para menú, cobertura y preparación. Se conserva
el archivo como respaldo ante fallos del proveedor o de la base.

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
ni alérgenos. La ingesta usa únicamente platos activos y guarda fuente, versión, tenant y
configuración del embedding junto con los fragmentos.

## Publicación y consulta

1. Editar `parrilladas/menu.json` e incrementar `content_version`.
2. Ejecutar las pruebas y desplegar la imagen actualizada del API.
3. En el entorno del API, con las credenciales de su cuenta de servicio:

   ```bash
   python -m parrilladas.modules.assistant.knowledge_cli ingest
   python -m parrilladas.modules.assistant.knowledge_cli show
   ```

La ingesta llama a Google y genera consumo; no contacta a clientes. Una carga idéntica
no vuelve a generar embeddings. Si falla algún embedding, no publica nada. Una nueva
versión sustituye atómicamente a la activa y conserva la anterior como historial.
No ejecutar estos comandos en Admin, que no tiene acceso SQL ni credenciales Google.

En Admin → Asistente → Conocimiento del negocio se ven la versión publicada, la fuente,
el modelo y los textos exactos que puede recuperar Gemini. Esta pantalla es de consulta;
la edición continúa en el archivo, según la preferencia acordada.
