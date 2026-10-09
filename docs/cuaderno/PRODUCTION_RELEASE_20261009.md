# Release de producción de Cuaderno Cocina — 9 de octubre de 2026

## Estado actual: V12 admitida en producción

La [CI oficial V12 37905852791](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37905852791) completó **9/9 jobs SUCCESS**: **626 casos raíz, 742 bajo `/cuaderno-cocina/` y 9 de cantidades, 1.377 PASS**, más **17 registros G7** con cadena verificada offline. Frontend: 395 pruebas y TypeScript/build PASS; backend Cuaderno: 620; nativo: 1.296 y 21 subpruebas; tooling: 463 Python y 11 Node. Estas cifras corresponden a V12 y no suman campañas históricas.

La fuente congelada es `643e37ada841b182890daf77790e3e21768d5952`, SHA `9205105e02bccdb45ff5cc6048720e2a293532b660db2c3ee46e52394f52623b`. La imagen local atestada `sha256:0f2cb8a04379038b907b1f7de95c56cd372e3fc277c7d3d1f4becc276fcd3ee3` está saludable en el web `33de2a64d5054a05c67130a5971b9b6d086ca92ebde7214e550ee609ea69cb88`; la base persistente se conserva. El ID de configuración del archivo de CI es distinto: `sha256:edf352177c7cc470589326fd6b686177380c31198972d2d7e3b9d07be6185b21`.

La aceptación anónima aprueba **4 casos y 12 PNG**; se inspeccionaron dos login originales. Cantidades aprueba nueve cuentas/cuatro anchos, con **180 PNG originales** y **24 tarjetas revisadas manualmente**, hashes y dimensiones concordantes. La copia OLD y su restauración aislada pasan. El deployer original conserva su **FAIL** en `new-web-healthy`; la continuación separada **PASS** instaló únicamente wrapper/unit de backup y recargó systemd, sin recrear web ni mutar DB o entorno. La frescura OLD se refiere al inicio real del despliegue original, no al momento de la continuación.

**Producción V12 admitida el 9 de octubre de 2026 a las 11:49:25 UTC.** El recibo separado `consulta-v12-final-production-admission.json`, SHA `6bd0ac7d5474098604d30ad5f2e675fe8a8791190676d0cdae7528044949613d`, declara `production_admitted=true`. La observación final del host PASS conserva su propio campo de admisión false y queda vinculada por SHA `e7dabf4fdf7c44cf31f98267f4e88827aab10eeb6526b1de9ee2b4783544739d`; no se alteran los recibos previos.

La campaña pública V3 completó **diez cuentas, tres Consulta, veinte comprobaciones anónimas y trece PNG**, sin errores de navegador ni infracciones de red; collector SHA `b23b6adaf62102477e426ccf26f18faacb6fd9e343e1a9e4e6e31285a01fb7a9`. Se revisaron sus seis originales Consulta a 1440×900. La copia coherente NEW `20261009T113538Z-73dff108e3a0` y el restore nativo aislado PASS verificaron **123 tablas, 330 migraciones, filas, media y 119 secuencias**. El fingerprint DDL figura no comparado; no se afirma esa verificación.

El cierre conserva la DB, **27 recursos propios de clon detenidos**, **19 contenedores ajenos exactos** según sus baselines tipados y Caddy con seis sitios activos y sus 220 pins. El timer está habilitado, activo/en espera y su servicio inactivo. En el boot actual `46317f80-a29d-4877-9072-43038cb02eed`, la observación completa y la ventana desde el despliegue registran cero OOM; los seis más tres OOM históricos permanecen separados, sin afirmación entre arranques ni atribución de actor. El espacio libre puntual final fue 3.696.984.064 bytes, aproximadamente 3,44 GiB.

La etiqueta anotada [production-20261009-643e37a](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/tree/production-20261009-643e37a) está publicada y verificada remotamente: objeto `3b0e1f84e2fe94b21bfb40b7504f66361855ae38`, destino `643e37ada841b182890daf77790e3e21768d5952`. V1/V2 y probes conservan sus resultados originales; el PASS completo V3 no demuestra la causa de los fallos anteriores y conserva los mismos criterios.

El benchmark V12 mide p95 de formatos **125,726 ms**, movimientos **87,549 ms**, servicios **93,939 ms** y escandallo **23,612 ms**, dentro de listas **800 ms** y escandallo **300 ms**. Es DRF APIClient en proceso, cinco usuarios por tres rondas, PostgreSQL 16.15 sin JIT, Python 3.13.16/Django 5.2.17 y cuatro CPU visibles; no mide Internet, LCP/INP ni dispositivos físicos. Los registros históricos posteriores conservan su candidato y fecha; este cierre sustituye sus afirmaciones de estado actual; las limitaciones operativas configuradas siguen vigentes.

## Cambios del producto y alcance de V12

Las cantidades nativas se conservan como cadenas decimales exactas en API, SDK y formularios, con coma decimal normalizada, límites 32/16 y escalado validado antes de mutar. El calendario completa cargas y permite recuperación tras fallos; el registro de vistas usa bloqueo Space→Recipe para evitar el deadlock reproducido con PostgreSQL real.

Consulta recibe avisos claros en Esencial, Profesional e Integral. Portada/cabecera/navegación ocultan Crear/Importar; ficha oculta edición, duplicación y variantes. Las URL directas de edición e importación muestran el rol requerido y Volver a recetas, sin formularios mutadores. Conserva exportación JSON GET, favoritas personales y reglas nativas del calendario. Cocina y Responsable mantienen sus flujos. La UI exige membresía activa única y revalida permisos tras operaciones asíncronas; el servidor mantiene su autorización.

V12 conserva la aplicación V11 y corrige el harness Consulta: valida los bytes reales del archivo JSON descargado, prepara la portada existente al volver y exige el título exacto visible en móvil/escritorio. Mantiene GET 200, cuerpo terminado, descarga sin fallo, POST 201 de vista, 27 proyectos, collector estricto, presupuesto de 8 s y cero retries/skips añadidos. Regresión local: 14 PASS; TypeScript E2E: cero diagnósticos en 17,662 s. El presupuesto p95 de listas de 800 ms fue autorizado sin cambiar CPU; no se presenta el aumento del presupuesto como optimización.

## Recibos de despliegue y campañas públicas

El web V12 se creó dentro de la ventana original de despliegue y quedó saludable a las 10:49 UTC. El recibo original `consulta-v12-deploy-fd0ccaeb5910/result.json`, SHA `c6f9994c383d8725c72f32a359876627c115b371d3923395d868d4e1d23beb66`, conserva FAIL por la observación del trigger de un servicio ajeno. No se atribuye su actor ni causa.

La continuación `consulta-v12-posthealth-continuation-actual-v1.json`, SHA `4ddb58d20c32d72314f2ac6e876181bb5a44b7d21f466d9108cd2bfe69905cd9`, conserva PASS separado: sólo instaló el wrapper/unit preparado y ejecutó daemon-reload. Revalidó runtime, DB, entorno, host, fuente e inputs originales; no recreó web, no mutó DB y no hizo rollback. El fallo original permanece inalterado. La copiaOLD era fresca al inicio real del despliegue; no se afirma frescura al continuar.

La campaña pública V1 terminó 9/10: las diez cuentas completaron login/perfil/edición/rol/navegación/captura/logout y veinte comprobaciones anónimas, sin errores de navegador ni límites infringidos; IntegralConsulta falló al esperar la última navegación tras logout. V2 terminó 3/10, tras completar esas acciones en las primeras cuatro cuentas, con otra espera fallida en EsencialConsulta. Probe1 terminó 3/4 y observó una petición estática sin respuesta registrada; no demostró que fuera una precarga prescindible. Probe3 aprobó 4/4 con los mismos criterios y sin ignorar peticiones ni ampliar plazos. Estos resultados se conservan separados y no prueban una causa ni un fix de aplicación.

La campaña completa V3 terminó PASS a las 11:35 UTC con diez cuentas, tres Consulta y veinte comprobaciones anónimas. Conserva guardas de runtime y red, logout y los plazos originales; cuenta diez capturas dashboard y tres de importación bloqueada, con cero errores e infracciones. Sus metadatos de diagnóstico omiten credenciales, textoDOM, consultas y cabeceras libres. La revisión visual de los seis PNG Consulta originales de V3 mostró aviso español completo, controles de vuelta/exportación legibles y ausencia de formularios de importación. Sus hashes, bytes y dimensiones coinciden con el collector. La prueba privada visual tiene SHA `eb067c9c72051eb2f9e639c9a58b8113a6926d1d5466f3ed7174d7214ba671b1`; no certifica WCAG ni dispositivos físicos. La inspección histórica de V1 conserva su campaña9/10 fallida.

## Puertas restantes para admitir el release

1. CampañaV3 completa 10/10 y prueba nativa vinculada de las tres Consulta, con errores e infracciones cero.
2. Copia coherente NEW y restore nativo aislado de la imagen/source actuales; filas, migraciones, media y 119 secuencias comprobadas.
2. Observación final del host, recursos propios/ajenos, kernel del arranque actual, timer y linaje de reinicio autorizado.
3. Recibo explícito de admisión, evidencias con hashes y publicación de cierre.

La copia OLD/restore OLD ya pasan. No se hereda la admisión histórica de `c79` ni la campaña V8 para estas puertas. El arranque externo observado hacia las 06:31 UTC es `46317f80-a29d-4877-9072-43038cb02eed`; su observación puntual previa registra cero OOM, conservando aparte6+3 OOM históricos. Los cambios ajenos tipados mantienen IDs, imágenes y montajes exactos por observación; cualquier deriva posterior debe rechazarse, sin atribución de actor. La observación final V12 quedó aprobada según el cierre indicado arriba.

## Historia, informes y límites operativos

V11 terminó cancelada: seis jobs SUCCESS, dos FAILURE y G7 cancelado; raíz 617 PASS y 9 FAIL y prefijo 733 PASS y 9 FAIL del harness de exportación; cantidades no se ejecutó. V9 conserva 394/395 pruebas frontend y fallo de dependencia en harness; V10 conserva 395 PASS y fallo de TypeScript. V8 conserva 1.323 casos, G7: 17 registros, diez accesos públicos, copia/restore y host saludables como resultados históricos. Su bienvenida independiente guardó únicamente dos flags autorizados mediante PATCH 200, pero falló después en home-ready y no se reclasifica PASS. V6 mantiene el fallo agregado de geometría; V7 mantiene su fallo de prefijo y cantidades sin ejecutar. Se conservan originales, logs, capturas y recibos de cada candidato.

- [Informe técnico de todas las funciones y planes](INFORME_TECNICO_FUNCIONES_Y_PLANES_20261009.md): catálogo, contratos, roles, límites y archivos de la fuente congelada.
- [Funciones y comparación con alternativas](INFORME_PRODUCTO_Y_COMPETENCIA_20261009.md): investigación de fuentes oficiales del 9 de octubre, con sus límites.

Las diez credenciales se entregan en `CUENTAS_PRIVADAS.md` fuera de GitHub, nunca en estos informes. SMTP de recuperación y copia remota siguen sin configurar; un backup local no acredita offsite. Los precios de Esencial: 500 € + 17 €/mes, Profesional: 1.000 € + 20 €/mes e Integral: 1.500 € + 30 €/mes son informativos, sin cobro ni suscripción automática. PWA no promete recetas privadas completamente offline. **La aceptación final está acreditada por el recibo separado de admisión; las limitaciones operativas indicadas permanecen vigentes.**
