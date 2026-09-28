# Decisión: repositorio propio, código derivado de Tandoor

## Qué significa “nuevo repo”
Sí: un repositorio propio `cuaderno-cocina`, inicialmente privado y vacío en GitHub cuando el propietario decida crearlo. No: código desde cero, `git init` sobre una copia sin historia o reescritura de Tandoor.
El bootstrap clona Tandoor conservando historia mediante clon parcial, verifica la versión fijada, renombra `origin` a `upstream`, deshabilita su push y crea la rama local `cuaderno/main`. Añade este paquete sin sobrescribir archivos heredados. Publicar un `origin` nuevo es un paso posterior manual; el script NO escribe en GitHub.

## Arquitecturas consideradas
| Opción | Decisión | Motivo de diseño |
|---|---|---|
| Derivado Tandoor con extensiones modulares | Elegida | Conserva la interfaz preferida y gran parte del dominio existente. |
| Cuatro aplicaciones desplegadas, enlazadas por API | Descartada por defecto | Cuatro autenticaciones, identidades de alimentos, versiones y operaciones no atómicas. |
| Copiar frontend Tandoor y crear backend nuevo | Descartada | Reescribe contratos y reproduce bugs ya resueltos. |
| Reescribir todo en un framework favorito | Descartada | Contradice reutilización, coste y mantenimiento. |
| Adaptación selectiva de funciones de otros repos | Elegida | Comparar comportamiento, portar pequeñas piezas y tests al stack de Tandoor. |

Mantener base no significa conservar cada problema: se permiten patches upstream justificados, pero deben tener test y anotación de mantenimiento.

## Alcance contractual
El usuario indica permisos contractuales externos para los proyectos. Se acepta esa premisa sin verificar un documento no aportado ni volver a bloquear la estrategia. Mantener avisos y un registro por fragmento reutilizado. El contrato y datos personales no van al repo. No afirmar que la licencia pública cambió o que todas las dependencias están cubiertas por un contrato que no hemos leído.

## Qué se ha comprobado al preparar este kit
Mediante lectura remota, no ejecución: Tandoor 2.6.15, SHA en lock; Vue3/Vuetify/Vite, Django/DRF, Python 3.13 en Dockerfile; modelos Space, Food, Unit, MealPlan, ShoppingList, InventoryEntry/Location/Log. Las notas de esa release incluyen correcciones de aislamiento/permisos. Mealie/KitchenOwl/Grocy están fijados como referencias, no aplicaciones runtime.
No se ha medido rendimiento ni instalado la aplicación en este entorno. El bootstrap se valida con repositorios locales sintéticos. G0 debe obtener pruebas del producto real.

## Presupuesto y producto
Se reutiliza para reducir desarrollo, no para prometer que adaptar es gratis. La cifra comercial no es una estimación verificada de horas. Esencial es la primera entrega. Las extensiones profesionales son inversión del producto y deben quedar diferenciadas de cambios particulares del cliente.
