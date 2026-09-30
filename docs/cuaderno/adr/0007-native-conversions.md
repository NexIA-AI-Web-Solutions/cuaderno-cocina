# ADR 0007 — Conversiones portables sobre UnitConversion nativo

Estado: catálogo/API nativa aprobados y commit90a2e6ba0; selector aprobado y commit3c7cdcc4b.
Densidad, precisión y finanzas aprobados en commitb20314bf0 con integración314PASS.
Este código está compilado en el previewed4, build173240Z PASS. Upgrade/restore final y aceptación G7 pendientes.

Tandoor ya tiene `UnitConversion`, relacionado con `Unit`, `Food` y `Space`, con
cantidades Decimal de precisión 32/16. El derivado ya disponía de BFS sobre esas filas en
`cuaderno.services.subrecipes.convert_native_quantity`, cuya precedencia depende del PK.
Se extiende ese conversor existente; no se atribuye su código a upstream. No se crea otra
tabla de conversiones ni se copia código de
Grocy, Mealie o KitchenOwl. El selector Vue usa las mismas identidades nativas.

El intercambio `cuaderno-recipes-v2` puede incluir un catálogo de conversiones; sigue
siendo opcional para documentos anteriores. Cada fila conserva identidad, alimento
opcional, unidades, proporción y orden documental. La unicidad nativa es dirigida y,
en PostgreSQL, la restricción con `food=NULL` no deduplica conversiones globales. Por
eso se preservan globales paralelas, inversas y self-edges, además de las conversiones
específicas. Un mapping solo reutiliza una fila existente si alimento, extremos y
proporción coinciden exactamente; nunca se resuelve identidad por nombre.

Crear parte del catálogo y mapear otra parte puede cambiar el orden de PK y, con él, la
ruta elegida por BFS. Antes de escribir se comprueba que los PK mapeados y las futuras
filas nuevas puedan mantener la precedencia documental en componentes ambiguos. La
comprobación incluye también conversiones nativas del destino que no aparecen en el
mapping: globales más específicas para cada uno de **todos** los Food resueltos. Si una
arista extra alcanzable desde unidades mapeadas cierra un ciclo, paralela o inversa y
puede cambiar la ruta, se rechaza con `conversion_precedence` y HTTP 409. Se permiten
árboles y hojas, self-edges, ciclos desconectados y conversiones de otros alimentos. Un
v2 sin catálogo conserva compatibilidad, pero no promete reconstruir un grafo omitido.

La conversión canónica de masa o volumen tiene prioridad. Cruzar masa y volumen exige
una conversión específica del Food; una global no se interpreta como densidad. La
escala usa Decimal, aplica merma bruta/útil una sola vez y calcula numerador antes de
dividir. Los productos intermedios se evalúan en un contexto local de precisión 64 sin
alterar el contexto Decimal del proceso. Los valores del catálogo se validan y persisten
en campos 32/16: sus entradas float, no finitas o fuera de precisión se rechazan. Los
resultados intermedios pueden necesitar más decimales; las fracciones periódicas se
evalúan con precisión de trabajo, sin prometer precisión racional infinita.

Lista, detalle y escritura nativos mantienen el Space y la visibilidad de
`Food.recipe`, incluidas recetas privadas. Importar ya bloquea la fila Space; create,
update y destroy de la API nativa deben tomar el mismo lock, dentro de `atomic`, antes
de resolver o guardar la fila fresca. Bloquear solo el importador dejaría una carrera
entre su snapshot del destino y un writer nativo, por lo que se descarta. El lock usa
solo el PK de Space y no materializa su metadata.

Evidencia histórica de los bloques antes del cierre: backend18/18 `084616Z`; prioridad19/19
`084148Z`; UI 6/6 `081657Z`; escritores nativos concurrentes RED4 `090833Z` y GREEN4
`091813Z` (49,213 s de tests, 91,174 s de runner). Densidad y precisión terminaron
GREEN19 `092335Z` después del RED de precisión `092054Z`. El intento intermedio
`091546Z` falló porque el propio oráculo truncaba el SQL de `pg_stat_activity` antes
del `FOR UPDATE`; no constituye otro fallo funcional. Privacidad anidada: RED6
`092624Z-conversion-write-visibility-bdaf5845` (seis fallos contando subcasos y error
funcional con Food=null), GREEN6 `092856Z` y GREEN11 fortificado `093138Z`: owner/shared,
revocación, nombres/plurales/ID, PUT/PATCH, FK ajenas y globales paralelas. En aquel
snapshot la revisión conjunta y regresión estaban pendientes; su cierre está registrado
abajo. Builded4 PASS173240Z posterior; recuperación y G7 siguen pendientes.

Actualización posterior: ACL fortificada12 GREEN `095022Z`, tras RED12 `094627Z`
por resolución de una fila antigua con Food ajeno y nombre igual al local. El paquete
de catálogo/API y selector tiene revisión independiente y los commits indicados; esa
revisión excluye el bloque matemático. Densidad21 GREEN `095504Z` y dominio18 GREEN
`094927Z`. La integración310 `100750Z` queda RED por validación financiera incompatible
con recurrencias64. La revisión halló además acumulación/escala28 en ficha de producción:
RED2 `101129Z` y GREEN2 `101303Z` tras reutilizar helper64/contexto local. Revisión y
regresión posteriores estaban entonces pendientes; resultados finales abajo. Build y
recuperación sobre esos cambios estaban pendientes; builded4 posterior pasó173240Z, recuperación final aún pendiente.

Los derivados financieros admiten coeficiente de hasta64 dígitos dentro de magnitud
`-32 <= adjusted < 32` (cero permitido): se elimina el límite textual de exponente32,
sin ampliar entradas `_money`/Property32/4. Finanzas13 RED `101603Z` (dos subcasos
de64 y recurring real1/3)→GREEN `101803Z`. Presentación monetaria reserva contexto
`max(64, adjusted+4)` para enteros, céntimos y carry; no altera `unrounded`. Un coste
de subreceta1e77 derivado de operandos que caben en32/16 provocaba InvalidOperation:
dominio19 RED `102003Z`→GREEN `102030Z` con display exacto. Revisor independiente
integrity_review_sol aprueba los nueve archivos matemáticos incluidos esos deltas;
integración general314 `102933Z-integration-539d2ce9` PASS452.443stest/501.667srunner;
lint `103108Z` PASS tras correccionescosméticas. Commitmathb20314bf0 revisado/aprobado.
Builded4 posterior PASS173240Z incluye estos commits; recuperación final pendiente. No aprobación G7.
