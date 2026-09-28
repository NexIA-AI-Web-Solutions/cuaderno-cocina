# 08 · Seguridad y privacidad por defecto

## Autenticación y permisos

Better Auth y su integración oficial con SvelteKit; sesiones en cookies protegidas. No passwords/cookies en localStorage, no algoritmo casero de hash, no token compartido entre clientes. Alta pública deshabilitada. El primer propietario se crea mediante inicialización local/operador seguro.

Recuperación sin proveedor de correo: herramienta administrativa con token temporal de un solo uso, revoca sesiones y fuerza nueva contraseña. No token en logs o Git. Integración de correo es opcional posterior; no bloquear la app por no tener SMTP.

Cada acción/endpoint vuelve a comprobar sesión, rol y capacidad de edición. Middleware/layout facilita pero no sustituye permisos en servicios. Rechazar recurso ajeno o inaccesible de forma coherente. Roles de Integral: responsable gestiona todo; cocina consulta fichas/planificación y registra consumos/desperdicios permitidos; consulta solo lectura. Permiso de lectura de costes separado y comprobado antes de serializar datos.

## Sesión y HTTP

Secure/HttpOnly/SameSite según integración documentada; origen fijo tras Caddy; protección CSRF, headers coherentes, CSP compatible con Svelte y sin `unsafe-eval`. Pruebas de carga real para evitar romper la hidratación al añadir CSP. Errores de login genéricos; rate limit persistido de forma acotada o equivalente probado para no evadirlo reiniciando proceso.

Solo confiar en headers de proxy desde el proxy configurado. No dejar Node escuchando públicamente ni confiar en X-Forwarded-For de cualquier origen. Las consultas y recursos privados usan control de cache; no caché compartida de recetas, sesión o exportaciones.

## Archivos

Imágenes permitidas JPEG/PNG/WebP decodificadas de verdad, con límite de bytes (5 MiB inicial) y píxeles (24 MP inicial). Convertir, quitar metadatos EXIF/GPS, dimensiones acotadas y nombre/clave aleatoria o por hash. No permitir SVG/HTML arbitrario. HEIC no se promete sin soporte comprobado; error claro con alternativa JPEG.

Archivos fuera de `static/`, lectura autenticada por ID, prevenir path traversal/symlink, no confiar en extensión o MIME enviado. Escritura temporal y rename atómico. No servir ficheros originales peligrosos.

Importaciones con topes de filas/tamaño/profundidad JSON, sin ejecutar fórmulas/macros. Export CSV protege celdas que empiezan por =,+,-,@ cuando sean texto susceptible de fórmula. ZIP: impedir rutas absolutas/.., limitar tamaño descomprimido, número y ratio de archivos. No descargar imágenes de URLs arbitrarias del CSV (riesgo de SSRF).

## Datos del cliente

Desarrollo y CI usan únicamente fixtures sintéticas. No enviar exportaciones reales a modelos, servicios OCR o sistemas de analítica por defecto. La autorización de acceder a la aplicación antigua se obtiene antes de hacerlo; usar export/API documentada y solo datos cuyo acceso haya autorizado el cliente.

No deducir filiación religiosa, salud o perfiles de comensales del nombre/contacto de Elisabeth. Esta herramienta trata recetas de su trabajo, no datos de Ad Laudem. Observaciones dietéticas son notas de receta, no historias clínicas de personas.

Logs estructurados con request ID, tiempos y errores saneados. No imprimir ingredientes, recetas, cookies, hashes de contraseña, reservas nominativas o contenido de importación por defecto. Auditoría guarda el mínimo necesario (actor, operación, ID, versión, fecha); acceso solo responsable.

## Copias y secretos

Configuración privada fuera de Git, ejemplos sin secretos. Backups contienen datos sensibles: permisos mínimos y cifrado cuando salgan del servidor. Ni el ZIP de release ni artefactos de CI incluyen DB o media del cliente. No telemetría externa ni CDN obligatoria.

Documentar retención, contacto de soporte, ubicación y acceso al servidor antes de producción. No etiquetar la app como «cumple toda la normativa» porque pase tests técnicos; la configuración y acuerdos reales con el cliente importan.
