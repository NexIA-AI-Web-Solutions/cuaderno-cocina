# ADR 0011 — Correcciones runtime y evaluación verificable de hallazgos

Estado: implementación local en validación. Esta decisión no certifica una imagen ni cierra G7.

## Problema observado

El escaneo real de la imagen de trabajo conservó 42 hallazgos y salida 2. Incluía herramientas npm dentro de la distribución Python `nodejs-wheel-binaries`, OAuthlib 3.3.1, coincidencias CPE de CPython y bibliotecas Alpine. No se puede resolver esto suprimiendo avisos, cambiando versiones declaradas o confundiendo el inventario frontend con el filesystem de producción.

La distribución CPython 3.13.16 incorpora seis correcciones que la regla CPE del scanner sigue asociando a otra rama de Python. Su archivo `poplib.py`, en cambio, todavía necesita el backport de CVE-2025-15367. Los paquetes Alpine zlib y BusyBox también necesitan correcciones reales. El Node incluido en la rueda Python contiene otra copia de zlib: corregir el paquete del sistema no corrige automáticamente esa copia.

## Decisión

1. OAuthlib de la aplicación usa 4.0.0 y django-allauth 65.19.7 conserva los extras MFA/social. La antigua prueba del backport 3.3.1 sigue ejecutándose en tooling aislado con sus propias constraints; esas constraints nunca se usan para construir o probar el runtime.
2. Se retiran únicamente npm, npx, corepack y headers no utilizados de la rueda Node. La funcionalidad nativa que necesita JavaScript debe conservar un intérprete probado. Su procedencia y biblioteca zlib efectiva se verifican por separado.
3. `poplib.py` recibe un parche upstream únicamente si versión y hash completos coinciden. La salida mantiene Python 3.13.16 y registra hashes anterior/posterior, commit, fuentes y licencia.
4. BusyBox y zlib se reconstruyen con la configuración y todos los parches originales del commit Alpine fijado. Las revisiones locales identifican el cambio; no se inventa una versión upstream. Los tests exigen una reproducción vulnerable en el control y el comportamiento corregido en la salida. Todos los applets de BusyBox se conservan.
5. El manifiesto de release liga los JSON de procedencia a la imagen. Las pruebas de la imagen comprueban versiones instaladas, hashes de archivos efectivos y comportamiento, además de los hashes de las fuentes del builder.
6. El scanner bruto permanece inalterado: conserva cada hallazgo, `ignoredMatches=[]` y salida 2 cuando encuentra coincidencias. Un evaluador separado solo puede devolver `reviewed-no-unresolved` si cada coincidencia tiene una prueba exacta y verificable. Nunca se denomina «clean» a ese informe bruto.

## Contrato de evaluación

Se vuelven a comprobar contexto, archivo de imagen, configuración OCI/Docker, informe, resumen, herramienta y base de datos fijadas. Cada match conserva su JSON completo y una huella que incluye CVE, namespace, artefacto, versión, PURL, ubicaciones, matcher y detalles. Duplicados, elementos desconocidos, cobertura incompleta, datos modificados, versiones distintas y pruebas que no corresponden a los archivos instalados producen fallo.

Las únicas pruebas admitidas son una release upstream exacta con sus fuentes primarias, un backport exacto con sus hashes y regresión runtime, o una corrección de distribución identificada expresamente. No hay rangos, comodines, excepciones de severidad, archivo genérico de exclusiones ni aprobación por ausencia de un CVE en secdb. El scanner y la evaluación siguen siendo dos resultados diferentes.

El runtime de evaluación se ejecuta con la imagen inmutable, sin red externa, sin mounts del host, sin privilegios, como UID 10001 y con filesystem de solo lectura. El ensayo HTTP de BusyBox usa exclusivamente loopback dentro de ese contenedor. Todos los artefactos se conservan bajo sus namespaces locales; no se sobrescribe evidencia.

## Licencias y mantenimiento

BusyBox mantiene GPL-2.0-only: se distribuye su código fuente correspondiente, configuración, parches y receta junto con la imagen. zlib conserva su licencia y atribución. Los parches tienen fuentes primarias y hashes completos; el parche BusyBox revisado de la lista upstream se describe como backport de una propuesta, no como una release upstream ya integrada.

Actualizar Python, Alpine, Node, scanner o base de datos invalida las coincidencias y pruebas anteriores. El nuevo candidato debe repetir la aceptación; un PASS unitario del evaluador nunca sustituye un escaneo y una prueba reales de esa imagen.

## Fuentes primarias

- [CPython 3.13.16](https://www.python.org/downloads/release/python-31316/).
- [Corrección poplib](https://github.com/python/cpython/commit/b234a2b67539f787e191d2ef19a7cbdce32874e7).
- [Corrección zlib](https://github.com/madler/zlib/commit/df84af25dc1942490e1d1c899a07619152a46148).
- [Propuesta BusyBox revisada](https://lists.busybox.net/pipermail/busybox/2025-November/091840.html).
- [Alpine aports fijado](https://gitlab.alpinelinux.org/alpine/aports/-/tree/e63efda2ffc3f7389eda3adbf5f569961d9b0d7a).
- [OAuthlib 4.0.0](https://github.com/oauthlib/oauthlib/releases/tag/v4.0.0).
