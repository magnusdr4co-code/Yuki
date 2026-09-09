# Pendiente: `BACKUP_GCS_BUCKET`

**Estado:** sin implementar. Es lo único de M3 que sigue abierto, y lo único de
todo el mecanismo de copia que **no depende del código**.

## Por qué importa, dicho sin rodeos

Hoy la copia diaria funciona entera: empaqueta lo irremplazable, la verifica con
`integrity_check`, y desde hace poco la propia instancia **la restaura cada
noche** para comprobar que sirve. Todo eso está hecho y probado.

Y todo eso queda en el mismo disco que el original.

Una copia junto a lo que copia protege de un borrado accidental, de una
corrupción de la base y de un despliegue que se lleve algo por delante. No
protege del escenario para el que existe una copia: **perder la máquina**. La
instancia es única, sin réplica —eso es el limitador L7— y el disco de una
`e2-small` es un disco.

El resultado actual **lo dice** en vez de sugerir que está a salvo:

```
⚠ No sale de la instancia: sin BACKUP_GCS_BUCKET: la copia queda en el mismo
  disco que el original y no protege de perderlo
```

Que lo diga es lo correcto. Que siga siendo verdad, no.

## Qué hay que hacer

El código ya está: `BackupManager._subir()` sube el archivo en cuanto hay bucket
declarado, con las credenciales de la cuenta de servicio (ADC). No hay que
programar nada — hay que crear el sitio y darle permiso.

1. **Crear el bucket**, en la misma región que la instancia para no pagar salida
   entre regiones:

   ```bash
   gcloud storage buckets create gs://yuki-respaldo \
     --project=yuki-prod \
     --location=europe-southwest1 \
     --uniform-bucket-level-access
   ```

2. **Ciclo de vida.** La copia es diaria y la instancia sólo conserva las últimas
   localmente; el bucket, si no se le dice nada, las guarda todas para siempre y
   la factura crece sola:

   ```bash
   echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":90}}]}' > /tmp/ciclo.json
   gcloud storage buckets update gs://yuki-respaldo --lifecycle-file=/tmp/ciclo.json
   ```

   Noventa días es una propuesta, no un dogma. Lo que no se puede es *no elegir*.

3. **Permiso mínimo a la cuenta de servicio de Yuki.** `objectCreator` y no
   `objectAdmin`: la instancia tiene que poder **escribir** copias y no poder
   borrarlas. Si un día algo va mal dentro de la máquina —o alguien entra— lo
   último que quieres es que pueda vaciar el sitio donde están las copias.

   ```bash
   gcloud storage buckets add-iam-policy-binding gs://yuki-respaldo \
     --member=serviceAccount:<la-cuenta-de-yuki>@yuki-prod.iam.gserviceaccount.com \
     --role=roles/storage.objectCreator
   ```

4. **Declarar la variable** donde corre el daemon (`docker-compose.yml`, el
   entorno de la VM o el secreto que corresponda):

   ```
   BACKUP_GCS_BUCKET=yuki-respaldo
   ```

## Cómo saber que funcionó

```bash
python3 cli.py backup --ensayar
```

Tiene que decir `✓ Fuera de la instancia: gs://yuki-respaldo/...` en lugar del
aviso de arriba, y además `✓ Comprobada: la copia vuelve a levantarse`.

Y el gemelo virtual deja de contarlo como limitador abierto:

```bash
python3 cli.py virtualize | grep L7
```

## Lo que sigue faltando después

Subir la copia **no** es lo mismo que saber que la copia subida sirve. El ensayo
nocturno restaura la copia local, que es la que acaba de hacer; nadie descarga la
remota y la abre. Una copia sin restaurar no está comprobada, y eso vale también
para la que vive en el bucket.

Cuando el bucket exista, merece la pena un ensayo mensual que baje la última
copia remota y le pase `scripts/restore_drill.py --copia <fichero descargado>`.
El guion ya sabe hacerlo; sólo hay que traer el fichero.
