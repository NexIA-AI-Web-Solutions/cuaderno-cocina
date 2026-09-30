# ADR 0010 — Conjunto exacto de versiones Python de producción

Estado: implementado, revisión independiente, contratos y build real comprobados. Build205924Z-local-up-4298bc82 PASS1321.767s, imagen a3c/fuente f191+worktreee8999. Pythonstage verifica153pins/pipcheck; runtime211202Z-python-lock PASS153/conjunto2009d15b y211213Z-pip-check PASS. La identidad completa está en STATUS; no bytes ni OS congelados.

Los builds ed4/933 con requisitos raíz fijados difirieron en cuatro versiones: PyJWT2.14→2.15, charset-normalizer3.5.1→3.5.2, filelock4.0.6→4.0.7 y w3lib2.4.1→2.5.0. La actualización PyJWT fue deliberada; las tres transitivas demostraron que solo fijar raíces no congela el conjunto instalado.

Se conserva `requirements.txt` nativo con extras, incluida `django-allauth[mfa,socialaccount]`. Las153 distribuciones observadas en933audit185939Z se fijan en `tooling/cuaderno/python-production.constraints.txt`. El Dockerfile aplica constraints al bootstrap pip/setuptools/wheel/setuptools-rust y a todos los requisitos de producción; ejecuta pipcheck y compara el conjunto instalado antes del backport OAuthlib. Copia las constraints al runtime como `PYTHON-PRODUCTION.constraints.txt`.

`python_lock.py` rechaza duplicados normalizados, pins no exactos, paquetes faltantes/adicionales/versiones cambiadas y JSON ambiguo. El PURL PyPI debe corresponder al nombre canónico y versión del componente, sin namespace/qualifiers/subpath. RED6subcasos/7tests195434Z→GREEN7/7 195519Z. SBOM933153GREEN195521Z, hash de conjunto `2009d15b8f39b8051a5afe772e90487f898f91a38fdb6de15f23e163799e01bb`; SBOMed4 control negativo193614Z rechaza las cuatro diferencias. Reviewfresh purchase aprobada. Commitlocal3ea8bf323.

Este cierre acredita VERSIONES, no byte-reproducibilidad: no se inventan hashes de archives a partir de metadata instalada, y APK/PEP517/OS quedan fuera. El inventario y el escaneo de avisos siguen siendo controles separados. No eliminar OAuthlib/advisories ni funciones sociales para obtener un audit artificialmente verde.
