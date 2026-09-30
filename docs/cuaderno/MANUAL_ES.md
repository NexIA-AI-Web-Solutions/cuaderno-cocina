# Cuaderno Cocina — uso local

La aplicación es Tandoor con módulos Cuaderno integrados. Preview local: `http://127.0.0.1:18081`, imagen591 con merma/mínimos, precios, preparación persistente y desperdicio con causa/valoración. Consulta STATUS para la identidad probada. La demo de desarrollo anterior sigue en `18080` y no sustituye la imagen recompilada. G7 permanece abierto.

Cuentas sintéticas, solo locales: `demo-esencial`, `demo-profesional` y `demo-integral`, contraseña de este ensayo `Demo-Cocina-2026!`. Cada una tiene su Space; no son cuentas de producción. El seed exige contraseña explícita y solo funciona sobre `cuaderno_demo` en entorno local.

```powershell
$env:CUADERNO_ENV='local'
python scripts/cuaderno/local_up.py
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
docker exec -e CUADERNO_ENV=local -e CUADERNO_DEMO_PASSWORD cuaderno-release-web /opt/recipes/venv/bin/python manage.py seed_cuaderno_demo
```

Docker Desktop debe estar disponible. El script reconstruye las dependencias Python desde los requisitos del checkout, compila el frontend desde `yarn.lock` y usa únicamente los contenedores/volúmenes `cuaderno-release`. No exige la antigua imagen local del pin. El primer build y las migraciones pueden tardar varios minutos. La identidad del build incluye HEAD y hash del contenido local, no presenta cambios sin commit como si fueran HEAD puro.

## Esencial

1. Entra y abre Costes.
2. Crea el alimento y la unidad en las pantallas nativas de Tandoor.
3. Registra el formato, por ejemplo garrafa de 5 L a 32 €. Sin existencias.
4. En la receta, el panel muestra el coste y el coste por ración. Cambiar las raciones de la vista no guarda la receta.
5. Si falta un precio, el total queda incompleto. No aparece como cero.
6. Para imprimir, abre la vista previa del navegador y comprueba que incluye el coste y sus avisos. Esta comprobación visual todavía no se ha ejecutado aquí.

## Profesional e Integral

Esas operaciones exigen subir la edición del espacio en `PUT /api/cuaderno/edition/` con `profesional` o `integral`. Un pedido no mueve stock. Una recepción usa clave de idempotencia. Planificar un servicio no descuenta existencias. Un alérgeno no declarado no se da por ausente.

En la demo ya hay un Space por edición. Los traslados nativos conservan historial dentro del mismo Household. No cambies una ubicación a otro Household ni la unidad/alimento de una entrada con historial; crea entidades correctas y registra movimientos explícitos. Los usuarios operativos solo acceden a su Household; el administrador del Space puede consultar todos.

En el panel Costes de la receta, Profesional e Integral permiten guardar precio de venta por ración y presupuesto por persona. Acepta coma decimal y hasta cuatro decimales de entrada; deja vacío para desconocido. Los indicadores muestran coste de ingredientes, diferencia respecto a venta y distancia al presupuesto con la política neta/bruta del Space. La presentación monetaria usa dos decimales HALF_UP. Esa diferencia no incluye trabajo, energía, alquiler ni impuestos y no representa beneficio neto. Confirmar un servicio congela estos valores; el JSON genérico no incluye las propiedades financieras, el backup completo sí.

En Producción, anota nombre, fecha local, comensales y receta. Confirmar guarda la ficha calculada sin descontar stock; los cambios posteriores de precios no reescriben ese coste. Cancelar conserva el registro sin descontar existencias. Producir exige confirmar la acción: en Profesional solo cambia el estado; en Integral consume los ingredientes del hogar asignado al crear el servicio, usando primero los lotes utilizables con caducidad más próxima. Si falta stock o la ficha tiene necesidades incompletas, toda la operación se rechaza. No registra existencias de producto terminado.

La ficha conserva las restricciones de las recetas privadas, incluidas sus subrecetas. Ser administrador o pertenecer al mismo hogar no permite leer un snapshot de una receta privada sin permiso nativo. Los servicios heredados sin fecha/hogar demostrables no reciben datos históricos inventados; conserva el registro y crea un servicio nuevo con datos completos para producir.

## Compras y conectividad

En Almacén, registra proveedores con el selector nativo y ofertas por formato. Crear un borrador o enviarlo no cambia stock. Recibe solo cuando llegue la mercancía: elige una existencia del mismo alimento/hogar e indica cantidad en la unidad del pedido; el backend convierte a la unidad del lote. Admite recepciones parciales. Revertir recepción conserva el original y actualiza stock y cantidad recibida juntos; no uses la reversión genérica de movimientos para ello. Cancelar evita nuevas recepciones, sin borrar lo ya recibido.

Reposición consulta servicios confirmados y stock utilizable del hogar, consolidando unidades y descontando el saldo una sola vez. Redondea envases hacia arriba. Sin precio declarado muestra desconocido, no cero. El precio de la oferta del pedido queda congelado; no es valoración FIFO del almacén ni beneficio neto.

Para desperdicio independiente, elige una existencia, cantidad y causa obligatoria (1–256 caracteres, sin controles). El historial conserva una estimación de reposición al precio declarado en ese momento; sin precio muestra desconocido. Una reversión añade una compensación, no borra el original. No registres además como desperdicio la merma ya incluida en la cantidad bruta de un servicio producido: duplicaría el consumo. La reversión genérica no admite movimientos vinculados a producción; la reversión completa documental del servicio sigue pendiente.

Sin conexión no se guardan ni encolan cambios. Recetas, media y páginas privadas requieren conexión. La actualización del service worker elimina sus cachés privadas antiguas y descarta la cola offline heredada sin reproducirla; no elimina datos del servidor. Una respuesta fallida conserva el formulario y la clave para reintentar la misma operación.

## Importar y exportar

El JSON `cuaderno-recipes-v2` conserva pasos, ingredientes, vínculos de subrecetas, rendimiento declarado, formatos y versiones de precios. Las identidades no se fusionan por parecido de nombres: si el destino ya tiene un alimento/unidad/formato, confirma su identificador mediante `mapping`. La importación es atómica e idempotente por fuente e identidad externa; contenido o mapping distintos para la misma identidad dan conflicto 409.

Las subidas del importador nativo tienen límite agregado de 50 MiB y 100 archivos. El proxy aplica 52 MiB a todos los cuerpos HTTP del build, incluidos otros adjuntos y multipart. Las descargas remotas opcionales se limitan a 10 MiB y pasan por el filtro SSRF. ZIP con rutas inseguras, symlinks o compresión extrema se rechazan. Estos límites no sustituyen la protección de red y cuotas de disco del servidor.

Previsualiza con `POST /api/cuaderno/exchange/?preview=1`: no escribe datos. Envía en la confirmación el mismo documento y el `preview_sha256` recibido; si cambia el documento o el mapping, se rechaza con 409 y debes previsualizar de nuevo. La API mantiene importación directa sin esa huella para clientes programáticos compatibles: valida igualmente el documento y los permisos, pero **no ofrece la garantía de comparación con una previsualización previa**. El flujo recomendado es preview y confirmación con huella.

Fotos, archivos y metadatos nativos avanzados se transfieren mediante la exportación ZIP nativa de Tandoor; este JSON declara que no los incluye y no descarga URLs. Tampoco incluye conversiones personalizadas, alérgenos ni ajustes fiscales del Space: no lo uses como backup completo. Para eso utiliza el procedimiento siguiente.

## Arranque de la demo existente

Docker Desktop debe estar disponible. Desde la raíz, para los contenedores locales ya creados:

```powershell
docker start cuaderno-g0-t002-db cuaderno-g0-t002-web
```

Este comando reanuda la demo existente; no instala desde cero ni recompila cambios. La entrega reproducible final desde commit permanece pendiente de cierre.

## Copia y recuperación local

El procedimiento completo usa `delivery_restore.py`; el antiguo `backup.py` solo hacía un dump y no acredita recuperación de media.

Con ambos contenedores demo activos, publicados solo en loopback y sin otras escrituras:

```powershell
$env:CUADERNO_ENV='local'
$env:CUADERNO_BACKUP_TARGET='release'
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
python scripts/cuaderno/delivery_restore.py --round-trip
```

Hace una copia coherente pausando únicamente la web local, vuelve a activarla en un bloque de limpieza y restaura en una base `cuaderno_restore_<identificador>` y un directorio media nuevos. Conserva los destinos para inspección. No cambia la base usada por la aplicación.

También conserva una base `cuaderno_restore_probe_<identificador>` para comprobar el dump antes de aceptarlo. El smoke funcional se ejecuta contra ese snapshot inmutable: login, permisos, costes y saldos no se comparan con una base viva que pudiera cambiar. Estos destinos deliberados se acumulan para diagnóstico; no hay limpieza automática ni eliminación de volúmenes.

La comprobación incluye las propiedades financieras y los documentos de servicio de las cuentas Profesional e Integral. El procedimiento de ejemplo usa Spaces DEMO de dueño único; no acredita que cualquier usuario de un Space real pueda leer todos sus servicios.

El ensayo065043Z del30 de septiembre sobre imagen591 comparó mermas, reserva sintética de6L, reposición, preparación y desperdicio/reversión:114 tablas,931 filas,110 secuencias,3 media y dos tareas reales. Bundle `data/cuaderno/backups/20260930T064711Z-99941210`, destino nuevo conservado. No acredita recuperación en producción ni rollback completo. Los smokes posteriores añaden auditoría legítima: la BD viva no debe compararse con el punto del dump.

El bundle queda en `data/cuaderno/backups/<fecha-identificador>/`: `database.dump`, `media.tar`, `manifest.json` y `restore-result.json`. Se comprueban hashes de los archivos, contenido/conteos de cada tabla, secuencias y hashes de cada media extraído. No edites el manifiesto para hacer pasar una copia dañada. Ante error se conserva el destino para diagnóstico.

Para recuperar otra vez un bundle local confiable:

```powershell
$env:CUADERNO_ENV='local'
python scripts/cuaderno/delivery_restore.py 'data/cuaderno/backups/<fecha-identificador>'
```

Sustituye el marcador por un bundle real. Cada ejecución crea otro destino nuevo. El procedimiento está limitado a los contenedores demo fijados; no sirve como orden de restore sobre producción. Las copias contienen usuarios, recetas y media: mantenlas fuera de Git y del intercambio público. El ensayo local no implementa retención, cifrado externo ni copias remotas automáticas.

## Comprobaciones y límites

```powershell
python scripts/cuaderno/check.py --list
$env:CUADERNO_ENV='local'
python scripts/cuaderno/check.py restore --allow-isolated-mutations
```

El runner conserva exit code y salida en `.cuaderno-runs/`. Un comando verificado puede fallar en una ejecución posterior; consulta el resultado real. Las pruebas de navegador, rendimiento y aprobación final siguen abiertas en `RELEASE_CHECKLIST.md`. No hay despliegue VPS ni prueba en iPad físico.

Para repetir la prueba HTTP contra la preview local, con las tres cuentas DEMO sembradas:

```powershell
$env:CUADERNO_ENV='local'
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
python scripts/cuaderno/check.py release-http --allow-isolated-mutations
```

Comprueba login/logout, coste y CSRF. Guarda venta1.25/presupuesto1 de Salsa DEMO en Profesional e Integral y crea/reutiliza un servicio reservado confirmado por cada Space. Son escrituras persistentes DEMO, no una prueba de solo lectura. No produce, recibe mercancía ni cambia stock. Solo admite el origen 127.0.0.1:18081 y las tres cuentas fijadas; no usar en datos reales. No sustituye la comprobación visual en navegador.

## Mermas y reservas de existencias

En Profesional e Integral, el panel de coste incluye «Mermas de ingredientes». Base bruta significa que la cantidad ya es comprada; base neta útil calcula la compra dividiendo por el rendimiento. Por ejemplo, 600 g útiles con rendimiento0,8 requieren750 g comprados. Una subelaboración usa su propio rendimiento; no admite una segunda merma sobre la misma línea. Esencial permite consultar, no editar. Cada guardado del panel lleva una revisión: si otro editor ha cambiado la ficha, se conserva tu entrada y se bloquea el reenvío. «Recargar datos» descarta cambios sin guardar solo cuando llega una respuesta válida. Los cambios de merma hechos por este panel registran autor y valores antes/después en la auditoría nativa; no se garantiza ese versionado para escritores externos que eludan el endpoint.

En Integral, Compras incluye «Mínimos de existencias». Selecciona alimento, unidad, cantidad positiva y opcionalmente una ubicación del propio hogar. Sin ubicación, la reserva es global. No combines reserva global y reservas locales del mismo alimento: elimina primero la anterior. Dejar cantidad vacía elimina el mínimo, no existencias. Al reponer se suman necesidades confirmadas y reservas; stock caducado no cubre la necesidad. Un exceso en otra ubicación no se traslada automáticamente. Los envases redondean hacia arriba y el panel muestra excedente; un precio desconocido no vale cero. La fusión de unidades solo acepta alias con igual dimensión y escala; unidades de documentos congelados conservan su identidad.

El preview aplica cookbook0243 y cuaderno0016. Build y HTTP fueron probados;
la migración desde pin para0016 sobre591 pasó el ensayo070137Z. Impresión y responsividad
visual siguen pendientes. Consulta STATUS para la identidad completa del servidor.

La herramienta local `release-yields` comprueba tres cuentas, permisos, CSRF y dos ciclos de merma con coste2.56→3.2→2.56. Restaura únicamente su propia revisión conocida y no altera stock ni servicios confirmados. No usar con datos reales; no sustituye una prueba visual ni valida servicios producidos.

## Historial e impacto de precios

En Ingredientes y precios, selecciona un formato existente y actualiza su precio sin crear otro formato. Un precio vacío sigue siendo desconocido; cero requiere marcar gratis explícitamente. El historial paginado se carga para la selección, con fecha, autor y versión vigente. Es una vista viva: no promete un snapshot transaccional entre páginas durante importaciones concurrentes.

En el panel de coste de una receta, abre la comparación de precio, selecciona formato y comensales, y pulsa Comparar. Cambia solo esa versión de precio; los demás ingredientes usan sus precios actuales. Si falta un precio anterior, su coste y diferencia son desconocidos, no cero. No es beneficio neto. La comparación no modifica raciones guardadas ni fichas ya confirmadas.

## Preparación de servicios

En Producción, cada servicio incluye «Ver preparación». Para nuevas confirmaciones, se congelan los pasos de la receta y sus subelaboraciones. Marcar/desmarcar conserva autor y fecha, sin cambiar coste, receta o existencias. Un conflicto conserva la vista y exige Recargar; no reenvía automáticamente. Mientras guarda no se puede recargar, y mientras carga no se puede marcar una tarea.

Un servicio histórico sin checklist permanece vacío aunque se reconfirme: no se reconstruyen instrucciones antiguas desde la receta actual. Producidos y cancelados son de solo lectura. Este bloque está implementado y probado en integración y por HTTP en el build local; su identidad se registra en STATUS. No se afirma aún prueba visual de esta pantalla.

El smoke local `release-preparation` crea/reutiliza hasta dos servicios
«Preparación HTTP DEMO», confirma y marca/desmarca una tarea en cada uno.
Comprueba conflictos y CSRF, sin producir ni mover stock. Los servicios y su
auditoría quedan guardados; restaurar el estado desmarcado no elimina esa
historia. Solo admite las tres cuentas DEMO y loopback18081. No encadenes varios
smokes con más de cinco logins por minuto/IP: conserva el límite y espera la
ventana si devuelve429.
