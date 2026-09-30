# Verificación local — 2026-09-29

Snapshot sobre `279ba8ad8c194a12e6dd8fe5eb5d2c56fbecb878`, con cambios sin commit. Resultados comunicados por el integrador y contrastados con el manifiesto local de restore. No certifican el siguiente commit ni sustituyen sus logs.

Rectificación del 30/9: el exit 0 de TypeScript de esta tabla fue vacuo por tsconfig raíz sin archivos; no comprobó la app. Ver `2026-09-30-continuacion.md` y STATUS para el comando efectivo RED, comparación con pin y los builds/tests posteriores. Se conserva esta tabla como historia, no aceptación vigente.

| Comprobación | Resultado observado | Alcance |
|---|---|---|
| Dominio puro | 27/27 pasan | Antes de últimas correcciones |
| Integración Django/PostgreSQL | 14/14 pasan; merge directo focal pasa después | Rerun final pendiente; revisión detectó cierre de conexiones de threads |
| Concurrencia PostgreSQL | 2/2 pasan | Carrera real |
| Upstream Spaces/userspace/shopping | 63/63 pasan | Selección de regresión |
| Upstream Food API | 52/52 pasan | No cubría colisión de formatos de referencia encontrada después |
| Suite upstream completa | 1276 pasan, 2 fallan, 1 warning; 364.45 s | `test_cooklang_integration` y `test_markdown_renderer`; falta reproducción limpia del pin para atribuir deuda |
| Formularios Vue | 7/7 pasan tras última corrección frontend | `node --test forms.test.mjs` en `vue3/src/cuaderno` |
| Vue TypeScript | exit 0 | `npx vue-tsc --noEmit` en `vue3` |
| Vue build | exit 0, Vite 8.1.2, 1278 módulos | Avisos sobre eval en mavon-editor y chunk >500 kB; PWA generada |
| Lint Cuaderno | exit 0, comprobado de nuevo | `docker exec cuaderno-g0-t002-web /opt/recipes/venv/bin/flake8 cuaderno`; serializer conserva 3 avisos anteriores |
| Validación media backup | 4/4 pasan | Rutas, duplicados, enlaces/tipos no regulares y contenido |
| Navegador | No ejecutable | Ningún Browser disponible; sin capturas nuevas ni certificación física |

## Backup y restore

Comando ejecutado desde la raíz en PowerShell:

```powershell
$env:CUADERNO_ENV='local'
python scripts/cuaderno/delivery_restore.py --round-trip
```

Resultado `passed: true`, conservado en `data/cuaderno/backups/*/restore-result.json`. Destino nuevo `cuaderno_restore_ffd79234a39d4f93903770804e95e479`; media en `data/cuaderno/restores/cuaderno_restore_ffd79234a39d4f93903770804e95e479`.

108 tablas, 860 filas, 104 secuencias y 2 archivos media verificados. Se comparan conteos y hashes MD5 del contenido ordenado de tablas, valores de secuencias y SHA-256 de cada media. SHA-256 del dump: `bafeb484ca76611447dc1e59e4f75716e96e872b7ef2bdd074c5b5f4d52441a0`. Restore 50.730 s; pausa web 39.524 s. Son tiempos del dataset sintético, no un SLA de producción.

El bundle registra commit, imagen, hash del diff rastreado y manifiestos. Ese hash no incluye archivos no rastreados: repetir el ensayo con el commit final para certificar la entrega. Dump/media quedan fuera de Git. No se restauró sobre origen ni se borraron volúmenes.

## Hallazgos en corrección

Identidad de retries de inventario nativo, saldo histórico de movimientos, ingrediente sin Food, expansión de subrecetas, roundtrip de descripción/privacidad/pasos, merge API con dos formatos de referencia y cierre de conexiones de tests concurrentes. No se consideran cerrados por los resultados anteriores.
