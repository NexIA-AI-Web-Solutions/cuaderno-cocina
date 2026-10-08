# Verificación posterior al reinicio con tres agentes

La verificación pública nueva de [Cuaderno Cocina](https://gex-dashboard.hopto.org/cuaderno-cocina/)
terminó con **58/58 casos aprobados**: cuatro anónimos y 54 de la matriz
autenticada. La ejecución funcional nueva en el clon sigue pendiente; este
informe todavía no acredita su finalización.

La fuente publicada sigue siendo `c79b2ce54c20f778524e3dcadfac0bc7e8053aa0`,
source SHA256 `1fb585ca77a057eda83900d8e7ea07ab13076f4a3d51cac59598753d3179fc5d`,
imagen `sha256:88bf041a552f273f46e3856bb02dfc663397ebf113fbe05ba579446245f255a9`.
El tag `production-20261008-c79b2ce` apunta a esa fuente. El push y las referencias
remotas se verificaron por SSH. Las notas viven en
`cuaderno/release-notes-20261008-c79`; no cambian la fuente congelada ni la imagen.

El reinicio programado ocurrió a las 06:30 UTC del 8 de octubre. Web y DB
propias estaban saludables al iniciar esta comprobación en el boot
`ee482e89-cbd8-4b2c-82f7-9183c93b991c`. Véase el
[informe de la release](../PRODUCTION_RELEASE_20261008.md) para la admisión,
el backup y el restore anteriores a ese reinicio.

## Navegador y cobertura pública

Se utilizaron tres agentes: preparación y análisis de la matriz pública,
auditoría independiente de resultados y capturas, y preparación de la
verificación funcional del clon. El líder ejecutó la matriz pública con
Playwright y Chromium local 151.0.7922.34. Los navegadores se serializan mediante
el mismo bloqueo, con unidades propias que limitan memoria, CPU y duración.

| Fase nueva | Casos aprobados | Cobertura |
| --- | ---: | --- |
| Anónimo | 4 | Login, aviso de recuperación, rutas privadas, cookies, manifiesto y API |
| Lectura autenticada | 36 | Nueve cuentas por cuatro resoluciones |
| Service worker | 9 | Registro, actualización, alcance y caché por cuenta |
| Login/logout | 9 | Inicio, revocación y conservación de otra sesión válida |

Las nueve cuentas cubren Esencial, Profesional e Integral, cada uno con
Consulta, Cocina y Responsable. Lectura usa 390×844, 768×1024, 1024×768 y
1440×900; worker y login/logout usan 1440×900. Se comprueban identidad y Space,
permisos, CSRF, cookies Secure bajo el prefijo, recursos reales, diseño adaptable,
receta pública y PDF con contenido válido. Estas pruebas no certifican un iPad
físico. El collector público mantiene su tratamiento anterior de `ERR_ABORTED`;
los diagnósticos HTTP adicionales se conservan y revisan por separado.

Las tres fases terminaron realmente con código cero. Cada una verificó nueve
logins auxiliares por el formulario de la web, nueve cierres de esas sesiones
y nueve cierres de las sesiones externas a los casos. Las semillas se guardaron
en memoria; no se inyectaron sesiones directamente en la base de datos.

## Denegaciones revisadas y datos conservados

Los 54 informes, las tres terminaciones y los registros de red están unidos
por sus SHA256 a los pins de esta ejecución. Hubo 22 respuestas GET403 en la
fase de logout. La revisión independiente y la comprobación del líder aceptan
dos clases exactas de este conjunto:

- 18 peticiones empiezan después del retorno de un logout confirmado con
  HTTP302 y ausencia de la cookie en el jar del SDK del mismo contexto.
- Cuatro del usuario sintético 7, contexto33, empiezan durante ese POST:
  `user-preference/`, `space/current/`, `user-space/all_personal/` y `space/`.
  Sus tiempos son +63/+77 ms respecto a POSTstart y −15/−1 ms respecto a APIend.
  Son coherentes con la revocación nativa dentro del POST antes de devolver302,
  mientras la SPA continúa arrancando tras el cambio de idioma del banco de pruebas.

Las cuatro concurrentes no se etiquetan como posteriores al retorno. No se
midió el instante exacto de revocación en el servidor ni el Cookie en el tráfico.
[`request.headers()` omite las cabeceras de cookies](https://playwright.dev/docs/api/class-request#request-headers);
la comprobación usa el logout emparejado y el jar del SDK. No se autoriza ninguna
otra respuesta4xx por este resultado. Los recibos del criterio previo fallido y
la clasificación inicial pendiente se mantienen intactos; la aceptación final
usa un recibo separado.

La limpieza efectiva retiró nueve usuarios sintéticos y tres Spaces.
No quedaban sesiones propias por retirar, pues sus logouts ya se habían
verificado. Las **502 filas ajenas a los fixtures conservan exactamente el
mismo hash que antes de crearlos**. Usuarios, memberships, preferencias,
profiles y households primarios se conservan. Había cero sesiones primarias;
su igualdad no constituye una prueba positiva con una sesión primaria existente.

## Capturas, límites y fallos del banco de pruebas

La fase anónima emitió 12 PNG con hashes y dimensiones comprobados. Cuatro
capturas nuevas del aviso de recuperación, una por resolución, tuvieron revisión
visual independiente: texto legible, retorno al login y ausencia de formulario,
solapes o desbordamiento. La matriz pública54 comprueba layout y PDF pero no
guarda PNG; no se atribuyen capturas a esa fase.

La recuperación por correo está desactivada en esta instancia. El formulario
nativo de login ofrece un enlace de ayuda y el destino informa
«Restablecimiento de contraseña no está implementado de momento», sin permitir
enviar correo. Se verificó esa conducta; no se probó envío SMTP. El SSR anónimo
no registra un service worker; se verifican su ausencia y el endpoint público.
La activación autenticada corresponde a la fase worker.

Se conservaron tres matrices anónimas iniciales fallidas por supuestos
incorrectos sobre enlace, traducción y worker anónimo. También se conservan
la primera READ con 36 FAIL y la segunda con 32 FAIL/4 PASS, causadas por el
formato y la preparación incompletos de las cuentas del banco de pruebas.
Las adaptaciones finales verifican el recibo de creación y preparan las nueve
sesiones por UI antes de los casos. El cuerpo54, su template, collector y
presupuesto por caso permanecen intactos; no se introdujeron retries ni skips.

## Recibos privados de esta ejecución

Los artefactos y credenciales se conservan fuera de Git, en archivos `0600`
dentro de `agent-evidence` protegido. Se publica sólo esta síntesis sin secretos.

| Recibo | SHA256 |
| --- | --- |
| Anónimo nuevo, summary | `650b25e55ceba307aabbb07f0f1d6528436924ae2f7289b2865719f71fb92768` |
| Verificación pública final de dos clases | `29fb3e132ae38e9925f8df8ccd7dbdbbeb5f927a2a1234b1e9d49e6db98ee911` |
| Limpieza sintética nueva | `592c5db42e994c890a8908f53a67e9e758539a7c2a3344eda755c1e3164fa553` |

La ejecución y revisión funcional nueva del clon, su parada y la comprobación
final del host se añadirán cuando estén efectivamente completadas.
