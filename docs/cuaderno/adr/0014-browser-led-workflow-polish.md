# ADR 0014 · Simplificar recorridos existentes desde evidencia de navegador

Fecha: 2026-10-11. Estado: aceptado para el candidato local.

La revisión real mostró formularios administrativos antes de los servicios activos, pedidos difíciles de distinguir, detalle de precios fuera del contexto visible y navegación móvil con acciones de configuración antes del trabajo diario.

Se reutilizan rutas, formularios, peticiones y componentes Vue/Vuetify. Se agrupan herramientas de producción en un desplegable nativo; se abre el detalle de precio existente en un diálogo; se enlazan nombres a destinos existentes; los filtros de fecha disparan la carga existente con cancelación y control de generación. Inicio conserva las tarjetas y el calendario de Tandoor.

La navegación utiliza las capacidades actuales de edición y rol. Los controles que guardan datos siguen requiriendo acciones explícitas; ninguna lectura confirma, produce ni recibe mercancía. No se introducen entidades, endpoints, cambios de stock o una segunda agenda.

Consecuencia: menos desplazamientos y mejor orientación sin alterar los contratos del negocio. El diálogo bloquea su cierre mientras guarda; los enlaces llevan al estado actual de la receta y no alteran las instantáneas congeladas del servicio.
