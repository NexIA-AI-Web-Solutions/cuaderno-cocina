# Contratos de cálculo y consistencia

## Valores numéricos
Usar `decimal.Decimal` desde strings, nunca `Decimal(float)`, y DecimalField. API serializa strings. Moneda inicial EUR. Precisión de trabajo al menos 28 dígitos, escala y límites de dominio documentados. Redondeo comercial a 2 decimales HALF_UP solo en presentación/total final. No sumar líneas ya redondeadas para calcular un total exacto; exponer diferencia de presentación si aparece.
Entrada española: aceptar `1,25` donde corresponde. No sustituir caracteres indiscriminadamente: rechazar ambigüedades de agrupación y separadores mixtos si no se pueden interpretar de forma segura. Negativos, NaN, infinitos y magnitudes fuera de límite: error.

## Unidades y formatos
Dimensiones: masa, volumen, conteo. 1 kg=1000 g y 1 L=1000 mL. Caja/bolsa/botella son formatos, NO dimensiones universales. Un formato necesita contenido y unidad. Conversión masa↔volumen solo con densidad específica conocida para ese Food; unidad↔masa solo con peso unitario declarado. No inferir que 1 mL=1 g, ni que una cebolla pesa siempre lo mismo.
Reutilizar Units/conversiones nativas si pasan estos contratos. Mantener id y Space. Un cambio del contenido del envase no debe alterar silenciosamente precios históricos.

## Escandallo
`precio_base = precio_envase / contenido_en_unidad_base`
`coste_linea = cantidad_necesaria_en_unidad_base * precio_base`
`factor_raciones = raciones_objetivo / raciones_base`
`coste_racion = coste_total / raciones_objetivo` para raciones >0.
Ejemplo: 5 L por 32 EUR, usar 400 mL => 2.56 EUR. Actualizar a 35 EUR => 2.80 EUR. Sin stock registrado, el resultado sigue existiendo.

Elegir precio actual a fecha de cálculo con regla determinista. Guardar historial y fuente; snapshot en producción confirmada. Cambiar un precio actual recalcula estimaciones, NO reescribe costes confirmados históricos.
Precios desconocidos no son cero. Estado `complete / incomplete / invalid`; `known_subtotal`, `total=null` cuando incompleto, lista de faltas. Ingrediente gratuito necesita indicación explícita. Texto “al gusto” sin cantidad no puede producir coste completo salvo exclusión explícita identificada en ficha.

## Mermas y rendimientos
Distinguir cantidad comprada y cantidad útil. Para rendimiento y en (0,1], cantidad comprada = cantidad útil/y. Etiquetar si la cantidad introducida es bruta o útil. No aplicar merma dos veces (Food y subreceta). Limpieza y pérdida/ganancia de cocción son factores distintos; la masa final cocinada puede aumentar (arroz), no forzar a <=1 un rendimiento de salida general.
Ejemplo: patata a 2 EUR/kg, 80% útil, 500 g útiles => 625 g comprados => 1.25 EUR. Rendimiento cero se rechaza.

## Subelaboraciones
Reutilizar vínculo Food.recipe si encaja; definir cantidad y unidad de salida, no confundir “1 ración” con “1 kg”. Salsa coste 6 EUR/rendimiento 2 kg; consumir 300 g => 0.90 EUR. Raciones escaladas de padre no cambian el rendimiento base hijo.
DAG sin ciclos; detección completa con ruta del ciclo; profundidad y número total de nodos limitados; referencias de otro Space rechazadas. Optimizar lotes evitando una query por arista. No recalcular todas las recetas del catálogo en cada listado.

## Margen
Mostrar “diferencia entre precio de venta y coste de ingredientes”, no beneficio neto. `food_cost_pct=coste_ingredientes/precio_venta *100` con ambos sobre la misma base neta/bruta explícita. Precio cero/incompleto => indicador no calculable. Costes laborales, energía, alquiler e impuestos no incorporados no pueden darse por cubiertos. Para cocinas sin venta: presupuesto objetivo por comensal.

## Borrados, merges y cambios
No borrar Food con historial profesional: archivar o PROTECT. Auditar merge nativo para reasignar price/package/allergen/inventory FK sin pérdida; tests con relaciones adicionales y permisos cruzados. Versionar conflictos y registrar autor.

Casos exactos en `tests/cuaderno/contracts/costing-cases.json`. Son fixtures de aceptación, no prueba de que upstream o la futura app los cumplan.
