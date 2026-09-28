# Seguridad, privacidad y aislamiento

## Baseline
Release Tandoor 2.6.15 incluye correcciones de permisos entre Spaces, exportación de recetas privadas, batch updates y rutas de archivo. Mantenerlas y escribir regresiones con datos sintéticos; no copiar componentes anteriores que reintroduzcan el fallo. Consultar advisories antes de publicar, sin actualizar mayor automáticamente.

## Autorización
Usar User/Space/Household/Groups y API nativos. Tests con dos Spaces, dos usuarios del mismo Space y una receta privada. Verificar list/detail/create/update/delete, bulk, export, print, imágenes, import, merge y nuevos endpoints. Toda FK debe pertenecer al Space autorizado. No confiar en Space recibido del frontend ni en esconder el menú.
Roles profesionales de consulta/cocina/responsable, mapeados a permisos nativos y nuevos mínimos necesarios. Validar si puede ocultarse precio a cocinero cuando se pacte; no inventar aislamiento como hecho antes de probarlo.

## Superficie web
HTTPS producción, cookies seguras, CSRF y CORS de origen único, ausencia de default admin/admin, registro público deshabilitado, rate limit de login, secrets fuera de repo. Recuperación de contraseña con transporte configurable y prueba local; no afirmar correo entregado sin SMTP real.
Sanear HTML/Markdown, imágenes y enlaces. Límites de upload. Media privada requiere autorización real; comprobar que un proxy no sirva un archivo privado por URL directa saltándose API.

## Importación y fetching remoto
Fetch URL opcional con protección SSRF: esquema permitido, IPs privadas/loopback/link-local/metadata bloqueadas, resolver/redirecciones comprobadas en cada salto, tiempos y tamaños limitados. El backend no ejecuta instrucciones del contenido importado. Por defecto datos reales no salen a APIs de IA, OCR ni analytics.

## Auditoría
Autor, Space, operación, id de documento y fecha. No contraseñas, tokens o recetas completas en logs. Fallos dan mensajes útiles sin stacktrace al cliente. Logs con rotación y retención acordada. Auditoría de dependencia y secrets en diff; no afirmación “cero vulnerabilidades” a partir de una única herramienta.

## Entorno
Tests solo contra BD temporal con nombre/prefijo de test; si URL apunta a producción, abortar. No levantar cuatro donantes. No usar `--yolo` ni desactivar guardrails. Solicitar autorización exclusivamente para acción externa real, no para terminar un formulario.
