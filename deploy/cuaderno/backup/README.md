# Backup programado

Estos archivos son ejemplos para un host Linux con el checkout en
`/opt/cuaderno/app`, el env file de producción en `/etc/cuaderno/production.env`
y un directorio local propiedad de `cuaderno-backup` en `/var/backups/cuaderno`.
El env file debe pertenecer al operador y tener modo `0600`; el directorio de
destino no puede admitir escritura de grupo u otros.

Instala las unidades en `/etc/systemd/system`, ejecuta `systemctl daemon-reload`
y activa el temporizador con `systemctl enable --now cuaderno-backup.timer`. El
usuario necesita permiso para usar el daemon Docker. Revisa ese privilegio como
acceso de administrador al host.

La herramienta crea un subdirectorio nuevo por ejecución, detiene `web`, rechaza
clientes de base de datos ajenos, genera el dump y el archivo media, y vuelve a
iniciar `web` en un bloque `finally`. No lee ni imprime valores del env file.

La retención, el cifrado y la copia remota deben implementarse como un hook externo
que solo reciba bundles cerrados que ya contienen `manifest.json`. Ese hook debe
cifrar antes de salir del host, comprobar la recepción remota y borrar localmente
solo conforme a una política documentada. No se incluye ni activa un proveedor
remoto en estas unidades.

Verifica periódicamente una copia con:

```text
/usr/bin/python3 /opt/cuaderno/app/scripts/cuaderno/production_restore_verify.py /var/backups/cuaderno/BUNDLE
```

La verificación crea recursos con el prefijo `cuaderno-restore-<uuid>` en una red
interna sin puertos publicados y los conserva para revisión. Nunca modifica ni
promueve `cuaderno-prod`. Si se facilita `--runtime-image sha256:...`, también
arranca esa imagen en el namespace aislado y exige que su readiness responda.
