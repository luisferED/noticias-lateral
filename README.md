# EL DEBER WEB: migración de NOTICIAS LATERAL a Browser Input

Overlay transparente de 1920×1080 para vMix. El panel ocupa x=1422..1919,
y=0..1079; la fotografía empieza en y=112. Incluye Flama Condensed,
rotación (15 s), refresco (180 s), hasta 14 noticias y QR local por artículo.
El escalado conserva la composición completa en ventanas menores.

## Configuración preparada

`compose.yaml` contiene únicamente `web`, conectado a la red externa
`dokploy-network`, con puerto interno 8095 (`expose`, sin `ports`). No publica
8095 en Ubuntu. Traefik debe acceder a `web:8095` mediante Domains de Dokploy.
No se fijan container_name ni etiquetas Traefik manuales. No hay SDK, servicio,
montajes ni host networking de NDI. El Dockerfile usa Python 3.12, Waitress,
usuario app UID 10001 y healthcheck HTTP independiente de la fuente externa.
Compose elimina capabilities y activa no-new-privileges.

La clave lógica del volumen sigue siendo `headlines-data`. Se exige
`HEADLINES_VOLUME_NAME` con el nombre físico exacto y `external: true`: un nombre
incorrecto hace fallar el arranque en vez de crear silenciosamente otro volumen.
Mantener además el mismo nombre de proyecto Compose y el mismo recurso Dokploy.
No añadir `name:` ni cambiar COMPOSE_PROJECT_NAME a un valor inventado.

## 1. Inventario y respaldo antes del cambio (Ubuntu)

Estos pasos los ejecuta el operador. No se ha accedido al servidor 172.20.16.195.
No detener la versión anterior todavía. En Dokploy guardar el Compose actual,
variables, nombre del proyecto, repositorio/rama, revisión Git y Domains (incluido
HTTPS, certificado, ruta y puerto). Guardar una etiqueta Git del commit anterior.

Identificar el contenedor web correcto, sin asumir su nombre:

```sh
docker ps --filter label=com.docker.compose.service=web
# Sustituir WEB_ACTUAL por el ID verificado del web anterior:
docker inspect WEB_ACTUAL --format '{{ index .Config.Labels "com.docker.compose.project" }}'
docker inspect WEB_ACTUAL --format '{{range .Mounts}}{{println .Type .Name .Destination}}{{end}}'
docker inspect WEB_ACTUAL --format '{{json .Config.Labels}}'
docker network inspect dokploy-network
```

Registrar PROYECTO_ACTUAL y el volumen montado en /app/data (confirmar también
el destino real en el Compose anterior). Si la ruta difiere, revisar el contenido
antes de migrar. Ejecutar `docker volume inspect VOLUMEN_REAL`.
Conservar copias de los resultados fuera del repositorio; pueden incluir datos
privados. Respaldar la cola sin escribir ni cambiar permisos en el volumen:

```sh
mkdir -p respaldo-el-deber
# Lectura de la cola actual; repetir inmediatamente antes del despliegue.
docker cp WEB_ACTUAL:/app/data/. ./respaldo-el-deber/
```

Para respaldo completo del volumen, usar el procedimiento de backups existente
del servidor. No usar `down -v`, `volume rm`, `volume prune`, ni borrar datos.
Comprobar permisos de lectura/escritura del directorio y archivos para UID 10001.
Si no son compatibles, resolver con el administrador y respaldo previo; no se
incluye un chown automático que altere permisos de la aplicación anterior.
Una caché antigua sin fotos/formato compatible se ignora y se obtiene una nueva;
la aplicación escribirá headlines.json al refrescar, por eso se requiere respaldo.

## 2. Archivos exactos para luisferED/noticias-lateral

Este directorio no es un checkout Git. Clonar el repositorio anterior en otra
carpeta y crear una rama de migración. Copiar a su raíz, sobrescribiendo:

- `compose.yaml`, `Dockerfile`, `requirements.txt`, `server.py`, `config.py`, `index.html`.
- `.dockerignore`, `.gitignore`, `.env.example`, `README.md`, `README.txt`.
- `assets/el-deber-verde.png` y `assets/fonts/FlamaCondensed-{Medium,Bold,Black}.ttf`
  (son tres archivos de fuentes).
- `tests/test_service.py`, `tests/test_rotation.cjs`.
- `tools/package.ps1`, `instalar.bat`, `iniciar.bat`.

No subir el ZIP original, `.env`, data/, backups, logs ni .venv. Revisar con
`git status --short`, `git diff --check`, `git diff` y `git ls-files`.
.gitignore no deja de rastrear secretos ya versionados: retirarlos del índice
con revisión previa y rotarlos si estuvieron expuestos. Retirar del índice los
fuentes/Dockerfiles/SDK de NDI que existan en el repositorio antiguo, después de
identificarlos; no se conocen aquí sus nombres exactos. El commit/etiqueta anterior
los conserva para rollback. No eliminar archivos de datos del servidor.
Hacer commit, revisión y push manualmente cuando esté aprobado. Este trabajo no
hace push ni despliegue.

## 3. Actualizar el recurso Dokploy existente

Usar el recurso Compose actual y `luisferED/noticias-lateral`; conservar su nombre
de proyecto, rama acordada y ruta `compose.yaml`. No crear otro recurso/proyecto.
Configurar variables en Dokploy:

```dotenv
HEADLINES_VOLUME_NAME=VOLUMEN_REAL_VERIFICADO
ROTATE_SECONDS=15
REFRESH_SECONDS=180
MAX_ITEMS=14
```

En Domains conservar `noticias.grupoeldeber-corp.com`, servicio `web`, puerto
contenedor `8095`, ruta `/`, HTTPS y certificado actuales. Confirmar que Dokploy
genera las etiquetas y conecta Traefik a dokploy-network. No añadir routers
manuales ni otro dominio idéntico en un segundo servicio. Revisar etiquetas y
routers existentes: no debe quedar otro web sirviendo el mismo Host tras el cambio.
El archivo fuente no basta para certificar las reglas dinámicas del servidor.

Validar en el contexto del proyecto actual antes del despliegue:

```sh
export HEADLINES_VOLUME_NAME=VOLUMEN_REAL_VERIFICADO
docker compose -p PROYECTO_ACTUAL config --quiet
docker compose -p PROYECTO_ACTUAL build web
```

No ejecutar `up` desde una carpeta paralela. Desplegar manualmente desde el recurso
Dokploy en una ventana acordada; puede haber una breve interrupción al reemplazar
web. Verificar el comando de despliegue de Dokploy: si usa `--remove-orphans`,
eliminará NDI al desaparecer del Compose. Para conservar NDI hasta validar web,
hacer primero una revisión de transición: reemplazar solo la definición web por
la nueva, añadir la red/volumen externo, y conservar **sin cambios** la definición
ndi antigua en esa revisión temporal. No debe incorporarse al Compose final de
este paquete. Revisar que ndi no tenga dependencia de un endpoint NDI retirado.
El Compose antiguo no está disponible aquí para generar esa revisión exacta.

## 4. Verificación posterior y Browser Input

```sh
curl -fsS https://noticias.grupoeldeber-corp.com/healthz
curl -fsS https://noticias.grupoeldeber-corp.com/api/config
curl -fsS https://noticias.grupoeldeber-corp.com/api/headlines
docker ps --filter label=com.docker.compose.service=web
# Con el ID nuevo verificado:
docker inspect WEB_NUEVO --format '{{json .State.Health}}'
docker inspect WEB_NUEVO --format '{{json .NetworkSettings.Ports}}'
docker logs --tail=100 WEB_NUEVO
```

Esperar healthy, confirmar red, volumen exacto y ausencia de HostPort 8095.
Comprobar en Ubuntu que no queda otro proceso publicando 8095. /healthz confirma
el proceso, no la disponibilidad de noticias: revisar también source_ok, items,
updated_at y la API. La fuente requiere salida HTTPS hacia eldeber.com.bo y fotos
hacia su CDN; el navegador/vMix también necesita acceso a las fotos.

Abrir `https://noticias.grupoeldeber-corp.com/` en navegador, revisar consola y red:
API, fuentes, fotos y QR deben responder sin 404/502 ni contenido mixto. Observar
una vuelta de 210 s y un refresco de 180 s sin reiniciar la cola. Probar ventana
1920×1080 y 960×540; el panel debe escalar entero, sin barras ni recortes.

En vMix: Add Input → Web Browser, misma URL HTTPS, Width 1920, Height 1080.
Activar transparencia donde la versión lo requiera; posición 0,0 y escala 1:1.
Superponer sobre una imagen de color: los 1422 píxeles izquierdos deben dejarla
visible y el panel derecho debe permanecer opaco. No usar captura de pantalla.
Verificar fuentes, animación, fotos, rotación y continuidad durante al menos 4 min.
Si el motor del navegador de vMix es antiguo, validar esta composición en esa
versión antes de retirar NDI. No se ha ejecutado vMix en este equipo.

Para cada noticia, comparar `items[].url`, enlace del QR y parámetro url de
`/api/qr.svg?url=...` (codificado). Escanear con teléfono usando datos móviles:
debe abrir la nota pública HTTPS de El Deber, nunca 172.20.16.195, localhost ni
el dominio del overlay. Probar varias notas, títulos largos y una rotación.
El endpoint solo acepta artículos HTTPS de eldeber.com.bo o www.eldeber.com.bo;
la URL exacta se codifica localmente sin servicios de QR externos. La existencia
actual de cada artículo y sus redirecciones se verifican con esa prueba real.

## 5. Retirar NDI únicamente después de aprobar web

Si se conservó con la revisión temporal, publicar manualmente el Compose final
solo web y actualizar el mismo recurso. Identificar su contenedor exacto:

```sh
docker ps -a --filter label=com.docker.compose.project=PROYECTO_ACTUAL --filter label=com.docker.compose.service=ndi
# Revisar labels, imagen y montajes antes de actuar:
docker inspect NDI_VERIFICADO
# Solo después de verificar navegador y vMix:
docker stop NDI_VERIFICADO
docker rm NDI_VERIFICADO
```

No usar `-v`. Si Dokploy ya retiró el huérfano, no repetir. Quitar de Dokploy solo
variables/montajes exclusivos NDI tras registrar sus valores para rollback.
No borrar volúmenes, datos, imagen anterior ni backups. Comprobar de nuevo dominio,
API y vMix. El puerto host 8095 deja de ser la vía de acceso; usar el dominio.

## 6. Rollback

Ante fallo: conservar logs, volver a la revisión Git/Compose anterior en el mismo
recurso Dokploy, restaurar sus variables y configuración Domains guardadas y
hacer deploy manual. Usar el mismo proyecto y volumen. Si el formato de caché
nuevo no sirve al web antiguo, restaurar la copia de headlines.json con web
detenido durante una ventana controlada, sin borrar el volumen. Restaurar NDI
mediante el Compose anterior si se retiró; comprobar requisitos SDK/montajes de
ese despliegue. Confirmar dominio, API anterior y recepción NDI. No ejecutar un
segundo stack con el mismo Host de Traefik. El rollback requiere conservar la
revisión, imagen y configuración anteriores, no solo este README.

## Desarrollo y pruebas

Windows: ejecutar instalar.bat y luego iniciar.bat; abrir http://127.0.0.1:8095/.
Sin Docker: instalar requirements.txt en un entorno Python 3.12+ y ejecutar
`python server.py`. PORT/HOST/DATA_DIR son opciones locales; Compose fija
0.0.0.0:8095 y /app/data. No abrir 8095 en el firewall para Dokploy.

```sh
python -m unittest discover -s tests -p test_service.py -v
node tests/test_rotation.cjs
```

Endpoints conservados: `/`, `/index.html`, `/assets/...`, `/healthz`, `/api/config`,
`/api/headlines`, `/api/qr.svg`. Sin fuente y sin caché válida, headlines responde
503; con caché y fallo externo devuelve 200 con stale=true y ok=false. La escritura
de caché es atómica. El healthcheck no consulta internet.

Para verificar realmente la imagen en Ubuntu antes del cambio, construir con
Compose y ejecutar un contenedor de prueba sin labels Traefik, sin publicar
puertos y sin montar el volumen productivo. Comprobar UID y healthcheck:

```sh
docker build -t el-deber-web:preflight .
docker run -d --name el-deber-preflight el-deber-web:preflight
docker exec el-deber-preflight id
docker exec el-deber-preflight python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8095/healthz').read().decode())"
# Esperar hasta el primer healthcheck (30 s) y revisar:
docker inspect el-deber-preflight --format '{{json .State.Health}}'
docker rm -f el-deber-preflight
```

El preflight es aislado y no sustituye la validación del volumen, Domains o vMix.
`tools/package.ps1` genera el ZIP de entrega en dist/ sin datos privados.

## Resultado de revisión local — 27 de octubre de 2026

Se revisaron todos los fuentes, scripts, pruebas, configuración y reglas de
exclusión del paquete (los binarios de fuentes/imagen se conservan).
Cambios: red Dokploy, sin publicación de puerto, volumen externo obligatorio,
capabilities eliminadas, eliminación de variables NDI sin uso, validación de
caché antigua y validación compartida de URL para extracción y QR. Se conserva
el diseño HTML/CSS y el Dockerfile con usuario sin privilegios.

- 12 pruebas Python: aprobadas (API, privacidad, QR, caché, concurrencia y parser).
- Prueba Node: aprobada; 14 noticias, 15 s/180 s, refresco sin reinicio de cola.
- Proceso Waitress real local: /healthz, /, /api/config y /api/qr.svg HTTP 200.
- Compose v5.1.4: config válido con nombre de volumen de prueba; sin esa variable
  falla como se espera. No se creó ningún volumen ni contenedor.
- Empaquetador PowerShell: ejecutado correctamente; ZIP en dist/.
- Docker Engine local no disponible: construcción de imagen y estado healthy del
  contenedor pendientes. No se certifican todavía Python 3.12 dentro de Docker,
  permisos del volumen existente, Traefik real, navegación visual, escaneo móvil
  ni Browser Input de vMix. Las pruebas Python locales usaron Python 3.14.
- No se accedió al Ubuntu ni se comprobó el Compose antiguo. No se hizo push,
  deploy, parada de servicios productivos ni modificación de datos anteriores.
