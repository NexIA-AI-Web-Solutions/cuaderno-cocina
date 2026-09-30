# ADR 0006 — Roles nativos vinculados a cada petición

Estado: implementado y revisado; integración218 y caracterización PostgreSQL17 pasan, incluido en el candidato local c07. No aceptación G7.

La caché nativa `GROUP_CACHE_<user_id>` no incluía Space ni membresía. Un
administrador en A podía conservar ese permiso durante 30 segundos al pasar a
invitado en B. La misma caché sobrevivía a una revocación de grupos, incluso
cuando se escribía directamente la tabla through usada por flujos nativos.

Se conserva UserSpace, Groups y la jerarquía guest/user/admin. No se introduce
otro sistema de roles. `has_group_permission` obtiene en una sola consulta la
membresía activa y sus grupos; requiere exactamente una membresía y verifica
su identidad contra usuario, Space y UserSpace de la petición. Los grupos se
memoizan solo dentro de esa petición. `no_cache=True` refresca ese snapshot.
Las claves compartidas antiguas se ignoran, sin borrar cachés ajenas.

Una revocación se refleja en la siguiente petición, no retroactivamente dentro
de una petición ya autorizada. Los writers que necesitan revalidar durante una
operación pueden solicitar el refresco explícito. Los requests upstream sin
Space/UserSpace vinculados conservan la selección de una única membresía activa.
Esto no implementa un rol nuevo de cocina sin acceso a precios ni amplía
permisos de superusuario.

Se descarta cachear por Space más señales M2M: los writers through nativos
pueden eludir esas señales, y su invalidación sería incompleta.

Evidencia: `040946Z-group-cache-isolation-d1ef94ec` RED11/13;
`041205Z-group-cache-isolation-d28f6fbf` GREEN13/13, PostgreSQL sintético,
revisión independiente Sol6.1. Commit `955cad4d7`; sin afirmar G7 ni cobertura
de una matriz profesional nueva. La suite205 posterior detectó una consulta
extra (15>14) en preparación; se optimizó la carga Space en middleware con
select_related en sus tres caminos, commit f6d2b474d, sin volver a cachear
permisos entre peticiones ni elevar el presupuesto. Preparación17 pasó en
042324Z; integración218 en 043228Z y permisos17 en 043447Z. Los cuatro casos
adicionales caracterizan acceso anónimo, request legacy, grupos y cambio de
binding dentro de una petición. No se suman como otra suite completa.
