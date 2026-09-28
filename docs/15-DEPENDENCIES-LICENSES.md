# 15 · Dependencias, mantenimiento y reutilización

## Resolver una vez, reproducir siempre

T001 prepara `docs/DEPENDENCY_BASELINE.md`: paquete, versión exacta, canal estable, fuente oficial, compatibilidad Node24/Windows/Linux, licencia y alertas. Crear el proyecto con generador oficial en una carpeta temporal si evita sobrescribir este paquete; trasladar solo archivos necesarios revisados.

Conservar un único gestor/lockfile. Fijar dependencias directas a versiones exactas y versión de packageManager. Instalar en CI/producción con lockfile congelado. Nunca resolver `latest` cada vez que el servidor arranca.

Módulos nativos: better-sqlite3 y sharp deben tener binarios compatibles o una compilación reproducible documentada. Comprobar driver en Windows y Linux; no introducir Python/C++ obligatorios para el cliente sin demostrar que faltan binarios. SQLite embebido requiere revisión de versión/parches, incluido historial WAL 2026.

## Reutilización selectiva

Usar frameworks/librerías mantenidos y componentes que encajen. No descargar «packs de recetas» sin procedencia, no copiar pantallas completas de un competidor, no quitar encabezados/avisos. Registrar licencia exacta de cada componente y subdependencia relevante en THIRD_PARTY_NOTICES.

Un componente sin licencia clara no se incorpora. Si una licencia requiere obligaciones incompatibles con la entrega prevista, sustituirlo o elevar decisión explícita; no resolverlo ocultando el origen. Antes de publicar un repo, el propietario decide licencia del código propio después de revisar dependencias.

## Mantenimiento proporcionado

Separar actualizaciones de seguridad y parches compatibles de upgrades de major. PR local/CI, pruebas y backup antes de cambios. No actualizar framework, DB y auth simultáneamente sin necesidad. Registrar versión de esquema y release para soporte.

No añadir SDK de IA, WebSockets, Redis, cola, motor de búsqueda, librería enorme de hojas de cálculo o framework de microservicios por una posibilidad futura. Cada dependencia nueva explica problema actual, alternativa nativa, tamaño, mantenimiento y test que la justifica.
