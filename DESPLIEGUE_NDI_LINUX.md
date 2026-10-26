# NOTICIAS LATERAL – EL DEBER: web y NDI® en Ubuntu

Preparación local, 26 de octubre de 2026. **No se ha desplegado ni instalado nada
en 172.20.16.195.** La web existente sigue siendo la referencia de producción.
El HTML, API, imágenes, tipografías y volumen web no se modifican en este cambio.

NDI® is a registered trademark of Vizrt NDI AB. [Información y herramientas NDI](https://ndi.video/).

## Arquitectura preparada

| Servicio | Ejecución | Red y API | Estado persistente |
| --- | --- | --- | --- |
| web | Dockerfile actual, Waitress, UID/GID 10001 | dokploy-network, puerto interno 8095, dominio actual | headlines-data:/app/data, sin cambios |
| ndi | Dockerfile.ndi, supervisor y emisor, UID/GID 10001 | network_mode: host, API http://127.0.0.1:18095/api/headlines | nuevo ndi-data:/app/ndi-data |

El único cambio de acceso de web es una publicación **127.0.0.1:18095 → 8095**,
para que NDI en host networking consulte la API sin depender de DNS ni Traefik.
8095 no se publica en las interfaces del servidor. El dominio
`noticias.grupoeldeber-corp.com`, servicio `web` y su ruta Traefik se conservan.
`ndi` no tiene dominio, puertos publicados ni red dokploy-network: sus sockets
usan la red real Ubuntu. No se puede resolver `http://web:8095` desde host mode.

Se eligió host mode para evitar NAT y facilitar descubrimiento mDNS y puertos
dinámicos de NDI. Esto comparte los puertos del host y exige inspección previa;
no significa que sea seguro emitir por todas sus interfaces. La configuración
privada del SDK selecciona la IP corporativa. No se añade otro Avahi al host.

La web y NDI conservan rotación 15 s, refresco 180 s, máximo 14 noticias,
1920×1080 BGRA con alpha sin premultiplicar y 30 FPS. NDI sigue renderizando con
Pillow, independientemente del escalado responsivo HTML. No hay audio ni GPU
obligatoria. Las dos salidas no están sincronizadas por fotograma.

## 1. SDK oficial y licencia: antes de usar el runtime

Obtener el SDK **estándar para Linux** desde la página oficial:
[NDI SDK](https://ndi.video/for-developers/ndi-sdk/). Descargar interactivamente
la versión ofrecida y conservar paquete, versión, arquitectura, hash y licencia.
No se incluye ni se inventa una URL directa de un instalador. No usar una DLL
Windows renombrada a .so ni una biblioteca de procedencia desconocida.

Se revisó la [guía oficial de licencia](https://docs.ndi.video/all/developing-with-ndi/sdk/licensing):
el uso está sujeto al acuerdo del SDK y sus exclusiones; hay requisitos de
atribución, enlace a NDI y avisos de terceros para distribución. La página pública
no sustituye el acuerdo incluido en la raíz del SDK descargado. **No se dispuso
del paquete Linux ni de ese acuerdo local; su aceptación y la autorización de uso
corporativo están pendientes.** Revisar también las obligaciones de terceros.
No asumir que una licencia gratuita autoriza cualquier redistribución. Si hay
dudas de ámbito comercial, consultar al proveedor antes de producción.

La imagen preparada NO contiene ni descarga libndi, SDK ni NDI Tools. El runtime
se monta de forma privada y de solo lectura desde Ubuntu; esto evita empaquetarlo
en una imagen o publicarlo en GitHub, pero no exime de aceptar su licencia de uso.
No distribuir la imagen con el runtime añadido sin revisar la licencia concreta.
No usar una prueba del Advanced SDK para emisión permanente: puede tener límites.

Elegir la biblioteca oficial de 64 bits correspondiente a `uname -m` y a las
capacidades de la CPU. El código usa C ABI mediante ctypes.CDLL, enteros de
64 bits, enums/int de 32 bits, punteros de 64 bits y alineación natural, sin pack.
Los layouts esperados actuales son 24 bytes (send_create) y 72 bytes (video_v2).
La verificación definitiva contra los headers descargados se describe abajo;
no declarar compatible cualquier versión/arquitectura solo por esos tamaños.

## 2. Inspección previa del servidor (solo lectura)

Conectarse a 172.20.16.195 con una cuenta autorizada. No pegar contraseñas en el
repositorio. Estos comandos no instalan ni cambian firewall o contenedores:

```sh
cat /etc/os-release
uname -m
lscpu
free -h
ip -br address
ip route
docker version
docker compose version
docker info --format '{{json .SecurityOptions}}'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker compose ls
docker network inspect dokploy-network
docker volume ls
ss -lntup
systemctl is-active avahi-daemon dbus
test -S /run/dbus/system_bus_socket
```

Confirmar Docker Engine Linux y Compose funcionales en el mismo nodo que la web,
red Dokploy y Traefik existentes. Este Compose está pensado para Docker Compose,
no `docker stack deploy`. Rootless/user namespace remapping y políticas D-Bus
especiales requieren validación adicional: no desactivarlas globalmente para
hacerlo funcionar. Revisar que 18095 esté libre en IPv4/IPv6, que no haya otro
emisor con el mismo nombre y qué aplicaciones usan los puertos NDI.

Docker documenta una limitación de aislamiento de publicaciones localhost en
versiones anteriores a 28.0.0; usar una versión corregida o una protección
existente validada por el administrador. No actualizar Docker automáticamente.
Si 18095 está ocupado, elegir un puerto libre y ajustar **ambas** variables
NDI_WEB_LOOPBACK_PORT y HEADLINES_API_URL.

Linux NDI necesita libavahi-client.so.3, libavahi-common.so.3 y avahi-daemon activo.
La imagen instala las bibliotecas cliente durante su build; utiliza el daemon y
socket D-Bus ya existentes del host. Si faltan, pedir al administrador que prepare
ese requisito en una tarea aparte. Este trabajo no instala servicios del host.
El montaje del socket D-Bus solo lectura sigue dando acceso al bus conforme a
sus políticas; validar que UID 10001 pueda usar Avahi sin ampliar permisos globales.
No se monta Docker socket, no se usa privileged ni capacidades adicionales.

Registrar el identificador del proyecto Compose actual y el nombre REAL del
volumen montado en `/app/data` mediante `docker inspect <contenedor-web-real>`.
Conservar ambos al actualizar y tomar respaldo mediante el procedimiento vigente.
No crear un proyecto nuevo para reemplazar el existente. **No Fresh Volumes,
down -v, prune, volume rm ni eliminación de archivos.**

## 3. Preparar runtime y configuración privados

Hacerlo manualmente DESPUÉS de revisar licencia y requisitos, fuera del checkout.
El SDK puede extraerse primero en una estación de administración; seguir su
instalador/instrucciones oficiales. No se entrega un instalador automatizado.

1. Crear, si no existen, `/opt/noticias-lateral/ndi-runtime` y
   `/opt/noticias-lateral/ndi-config`. Son carpetas nuevas dedicadas; no reemplazar
   una instalación compartida. Pueden cambiarse mediante las variables del panel.
2. Copiar del SDK autorizado la biblioteca Linux correcta y sus enlaces de
   versión necesarios a ndi-runtime. Mantener los destinos de symlinks dentro de
   esa carpeta. Debe existir `/opt/noticias-lateral/ndi-runtime/libndi.so`; si el
   paquete solo trae un nombre versionado, crear un enlace local hacia ese nombre
   o ajustar NDI_LIBRARY_PATH a `/opt/ndi/<nombre-real>`. No inventar el nombre.
3. Conservar los avisos/licencias necesarios junto al runtime privado. Dar permiso
   de lectura a UID 10001 y recorrido a sus carpetas; mantener archivos propiedad
   del administrador, sin permisos de escritura para el contenedor. No usar 777.
4. Crear un archivo NUEVO `ndi-config/ndi-config.v1.json` con este contenido.
   Si ya existe, revisarlo y combinar cambios manualmente sin sobrescribirlo:

Ejemplo de preparación MANUAL para carpetas aún inexistentes, desde una sesión
administrativa autorizada. Sustituir SDK_LIB_DIR por la carpeta REAL de la
arquitectura seleccionada y ya extraída desde el paquete oficial:

```sh
SDK_LIB_DIR=/ruta/real/del/SDK/lib/arquitectura-elegida
test -d "$SDK_LIB_DIR" || exit 1
test ! -e /opt/noticias-lateral/ndi-runtime || exit 1
test ! -e /opt/noticias-lateral/ndi-config || exit 1
sudo mkdir -p /opt/noticias-lateral/ndi-runtime /opt/noticias-lateral/ndi-config
sudo cp -a "$SDK_LIB_DIR"/libndi.so* /opt/noticias-lateral/ndi-runtime/
```

Si las carpetas ya existen, el ejemplo se detiene: inspeccionarlas primero.
No ejecutarlo sin aceptar la licencia. Copiar además los avisos requeridos desde
las rutas reales del SDK. Crear el JSON con un editor administrativo, sin
sobrescribir uno previo. Confirmar permisos de lectura/recorrido para UID 10001.

```json
{
  "ndi": {
    "adapters": { "allowed": ["172.20.16.195"] },
    "multicast": { "send": { "enable": false } }
  }
}
```

Esta selección es específica del SDK, no una regla de firewall ni una garantía
de que mDNS se anuncie solo en esa interfaz. Verificar las interfaces/ACL existentes
con redes. No añadir NAT, redirecciones NDI públicas, Bridge ni un Discovery
Server accesible desde Internet. Los grupos NDI no son control de acceso.
Si Ubuntu tiene interfaz pública, bloquear el despliegue hasta que el administrador
confirme el aislamiento corporativo. No se cambian reglas automáticamente.

Consultas de diagnóstico (ajustar ruta real si cambia):

```sh
ls -l /opt/noticias-lateral/ndi-runtime
readlink -f /opt/noticias-lateral/ndi-runtime/libndi.so
file /opt/noticias-lateral/ndi-runtime/libndi.so
sha256sum /opt/noticias-lateral/ndi-runtime/libndi.so
python3 -m json.tool /opt/noticias-lateral/ndi-config/ndi-config.v1.json
```

No copiar librerías propietarias al repositorio ni a assets. `.gitignore` excluye
DLL/.so, ndi-sdk, ndi-runtime y ndi-config; los contextos Docker usan listas de
archivos permitidos y excluyen binarios privados.

## 4. Environment y Domains en el proyecto ACTUAL de Dokploy

Repositorio `luisferED/noticias-lateral`, rama `main`, `compose.yaml`.
Revisar y subir manualmente el cambio cuando corresponda. No se hizo push.
Conservar el proyecto actual, sus identificadores y el dominio existente.

```dotenv
ROTATE_SECONDS=15
REFRESH_SECONDS=180
MAX_ITEMS=14
NDI_SOURCE_NAME=ED_DEBER_TITULARES_ALPHA
NDI_FPS=30
NDI_WEB_LOOPBACK_PORT=18095
HEADLINES_API_URL=http://127.0.0.1:18095/api/headlines
NDI_RUNTIME_HOST_DIR=/opt/noticias-lateral/ndi-runtime
NDI_CONFIG_HOST_DIR=/opt/noticias-lateral/ndi-config
NDI_LIBRARY_PATH=/opt/ndi/libndi.so
NDI_STALL_SECONDS=30
NDI_STARTUP_SECONDS=120
```

HEADLINES_API_URL debe sustituir cualquier valor anterior del panel o `.env`
que apunte al dominio/Windows. No modificar `.env` privado automáticamente.
Las rutas HOST_DIR son del host Ubuntu; NDI_LIBRARY_PATH es la ruta DENTRO del
contenedor. No colocar la ruta de una DLL Windows en Dokploy.
NDI_DATA_DIR y NDI_STATUS_FILE ya están fijados en Compose. Para ejecución fuera
de Docker también pueden configurarse como rutas escribibles.

En Domains conservar exclusivamente `web`, puerto 8095,
`noticias.grupoeldeber-corp.com`, su TLS y rutas actuales. No agregar dominio a ndi.
Revisar el Compose que genera Dokploy: ndi debe mantener `network_mode: host`,
sin `networks`, sin labels de router y con `traefik.enable=false`. Si la versión
del panel inyecta una red al servicio host, corregir esa configuración en el panel
antes de desplegar; Docker rechaza host+networks. No modificar redes de otros proyectos.

## 5. Pruebas de imagen y ABI antes de emitir

Estos son pasos MANUALES pendientes en una máquina Docker Linux autorizada.
No se ejecutaron aquí. No iniciar otra copia del proyecto de producción.
La imagen es libre de runtime propietario, pero requiere acceso a PyPI y a los
repositorios Debian durante el build. No se instala nada en el sistema Ubuntu:
apt/pip se ejecutan dentro del build de la imagen.

Desde un checkout de revisión con las dependencias Python NDI instaladas en su
propio entorno y un compilador C++ ya disponible:

```sh
docker compose --env-file .env.example config --quiet
docker compose build web ndi
python tools/verify_ndi_abi.py /ruta/real/del/SDK/include
```

El último comando compila una sonda temporal contra `Processing.NDI.Lib.h` oficial
y compara TODOS los offsets/tamaños y las constantes BGRA, progressive y
timecode_synthesize con ctypes. No necesita enlazar ni publicar el SDK. No usar
headers simulados como prueba de compatibilidad real. Si falta compilador o SDK,
dejar esta validación pendiente en una máquina de desarrollo autorizada.

Antes de emitir, usar `docker compose run` del MISMO proyecto real administrado
por Dokploy (mismo `-p`, archivo y Environment) o una imagen de revisión aislada:

```sh
docker compose run --rm --no-deps ndi python ndi_sender.py --check-runtime
docker compose run --rm --no-deps ndi python -c "import ctypes; ctypes.CDLL('/opt/ndi/libndi.so'); print('Dependencias cargadas')"
```

Estos comandos crean un contenedor temporal, sin fuente NDI ni frames. `--rm`
retira únicamente ese contenedor al salir, no los volúmenes. Los bind mounts
deben existir; `create_host_path: false` impide crear carpetas vacías por error.
La carga dentro de la imagen comprueba sus dependencias reales; `ldd` en el host
no demuestra compatibilidad dentro del contenedor. Un fallo debe resolverse con
el paquete/arquitectura/dependencia correcta, sin ejecutar como root ni copiar
bibliotecas arbitrarias. No usar la imagen hasta pasar la prueba oficial de ABI.

Con autorización futura, desplegar desde el proyecto existente de Dokploy.
No ejecutar `compose up` desde una carpeta nueva, porque crearía otra identidad
de proyecto y otro volumen web. El primer despliegue recreará web para añadir
su enlace loopback: programar una ventana breve, aunque no cambia sus datos.
No escalar ndi a varias réplicas. `restart: unless-stopped` permite recuperación
tras fallo/reinicio del host; también verificar que Docker/Dokploy arranquen al boot.

## 6. Healthchecks, conservación y recuperación

Web mantiene su healthcheck `/healthz`; indica proceso disponible, no garantiza
noticias ni escritura. Ndi espera a web healthy al inicio, pero sigue funcionando
con su última cola si web cae posteriormente.

Ndi conserva los paneles válidos en memoria ante error, cola vacía o respuesta
inválida de API; no reescribe con una cola vacía. Guarda titulares en
`ndi-data/headlines.json` de forma atómica y los recupera tras reiniciar. Las fotos
renderizadas se conservan en memoria mientras vive el proceso; no se cachean en
disco. Tras reiniciar, si tampoco hay acceso al CDN, se reutilizan los titulares
con el fondo de reserva original. El volumen web sigue siendo independiente.
El emisor ya no lanza un scraper web alternativo: consulta la API y usa su copia.

El proceso hijo usa el SDK síncrono; mantiene el buffer BGRA vivo hasta retornar
la llamada C. El SDK controla la cadencia con clock_video=true y se evita sumar
otra pausa completa. Solo después de envíos completados se actualiza, cada ~1 s,
`ndi-data/status.json` con frames acumulados, cola, FPS objetivo y receptores.
Los logs periódicos contienen frames/cola; web y ndi tienen logs rotados separados.

El supervisor comprueba avance independiente del hilo nativo. Si el hijo termina,
no logra enviar al arrancar en 120 s o su heartbeat vence durante 30 s, lo termina
(hasta SIGKILL si se atasca), sale y Docker reinicia el servicio. Docker NO reinicia
solo por estado unhealthy. SIGTERM normal permite cierre del sender. Si falta
runtime/permisos o la configuración es inválida, habrá intentos de reinicio:
revisar logs y resolver la causa, no ampliar tiempos para ocultarla.

Un heartbeat sano prueba que retornan envíos del SDK, NO que vMix reciba video.
La pérdida de receptores o una VLAN bloqueada no se resuelve reiniciando a ciegas.
La comprobación externa y la observación de tráfico completan la validación.

## 7. Diagnóstico tras el despliegue autorizado

Usar terminal del servicio en Dokploy o el directorio Compose REAL con su
Environment. Los siguientes son ejemplos de consultas, no se ejecutaron aquí:

```sh
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 ndi
docker compose exec -T ndi id
docker compose exec -T ndi python ndi_status.py
docker compose exec -T ndi python -c "import os,urllib.request; print(urllib.request.urlopen(os.environ['HEADLINES_API_URL'],timeout=15).read().decode())"
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8095/healthz').read().decode())"
docker compose exec -T ndi python -c "import os; print(os.access('/app/ndi-data',os.W_OK))"
docker inspect <contenedor-ndi-real>
docker inspect <contenedor-web-real>
curl -f http://127.0.0.1:18095/healthz
curl -f https://noticias.grupoeldeber-corp.com/api/config
ss -lntup
```

Inspeccionar usuario, red host solo en ndi, health, restart count, mounts de solo
lectura del SDK/config/D-Bus y volumen web original inalterado. Verificar que el
binding web sea 127.0.0.1 y que el dominio conserve respuesta y diseño.

## 8. Recepción desde otra PC y aislamiento de Internet

1. Detener manualmente el emisor Windows anterior para evitar dos fuentes con
   igual nombre; no necesita quedar encendido para el nuevo emisor Linux.
2. Desde la PC de vMix/Studio Monitor, confirmar ruta corporativa hacia
   172.20.16.195. En NDI Access Manager, si mDNS no cruza la VLAN, agregar esa IP
   a fuentes externas según las herramientas oficiales. Un Discovery Server
   corporativo es otra opción si ya existe y está autorizado; no se instala aquí.
3. Abrir NDI Studio Monitor y seleccionar la fuente que contenga
   ED_DEBER_TITULARES_ALPHA. El prefijo de equipo puede depender de hostname/Avahi;
   el nombre visible por sí solo NO demuestra qué IP está transmitiendo.
4. Agregar entrada NDI en vMix, seleccionar la misma fuente y comprobar
   1920×1080/30p, alpha sobre un fondo de color, tipografías, imágenes y transiciones.
   Observar por al menos 10 minutos, varias vueltas y actualizaciones de 180 s.
5. Verificar origen de paquetes en la NIC del receptor con Wireshark, filtro
   `ip.src == 172.20.16.195`, mientras se reproduce la fuente. Correlacionar los
   puertos con `ss` del servidor y el aumento de `connections` en status.json.
   Así se confirma el origen real, no únicamente el nombre. Con dos receptores,
   comprobar que ambos incrementen conexiones y se mantengan estables.
6. Desde esa PC, `Test-NetConnection 172.20.16.195 -Port 18095` debe fallar: la
   API privada es solo loopback. La web por dominio debe seguir funcionando.

Puertos oficiales para revisión por el administrador de red: UDP 5353 (mDNS),
TCP 5960 (consulta de fuentes), TCP 5961+ (flujos), UDP 5960+ (Reliable UDP),
TCP/UDP 6960+ y 7960+ según transporte, TCP 5959 solo si se usa Discovery Server.
No asumir que abrir únicamente 5961 basta. Revisar puertos realmente elegidos
por la versión instalada y autorizar solo redes/receptores corporativos.
No se aportan ni ejecutan comandos para abrir firewall o publicar estos puertos.
Antes de producción, el administrador debe verificar que ningún NAT/ACL pública
existente los exponga y que Avahi no anuncie la fuente en una interfaz pública.

## 9. CPU, RAM y tráfico: medición pendiente obligatoria

No hay mediciones de Ubuntu ni del codec real en esta preparación. Un frame
BGRA ocupa exactamente 8.294.400 bytes (7,91 MiB); a 30 FPS representa 248.832.000
bytes/s de datos crudos antes del codec, **NO** el tráfico NDI real. Solo los 14
paneles almacenados ocupan unos 111 MiB, más la cola nueva, transiciones, imágenes
temporales, Python y buffers del codec. Los picos son superiores; no fijar un
límite de memoria estrecho sin medir ni prometer un bitrate/consumo de CPU.

Con 0, 1 y 2 receptores reales, medir reposo, transición y actualización simultánea:

```sh
docker stats --no-stream <contenedor-web-real> <contenedor-ndi-real>
docker top <contenedor-ndi-real> -eo pid,pcpu,pmem,rss,comm
ip -s link show dev <interfaz-corporativa-real>
```

En host networking, Docker NET I/O puede no atribuir correctamente el tráfico.
Medir en la NIC con las herramientas ya disponibles o en el receptor/switch;
restar el tráfico de otros proyectos y anotar intervalo/receptores/transporte.
Comparar frames acumulados de status.json separados por 60 s (aproximadamente
1800 a 30 FPS), CPU, memoria máxima, bitrate real y paquetes descartados durante
10–30 minutos. No ejecutar stress tests en el servidor compartido. Si hay caídas,
resolver capacidad/enlace antes de producción; BGRA implica conversión de color.

## 10. Pruebas realizadas y pendientes

Ejecutadas localmente con Python 3.14 x64 Windows, sin SDK Linux ni Docker daemon:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
node tests/test_rotation.cjs
docker compose --env-file .env.example config --quiet
```

21 pruebas Python aprobadas: render/transparencia, bytes BGRA y metadatos,
layouts x64 esperados, carga Linux/Windows con mocks, error sin runtime,
conservación de cola y recuperación, health/watchdog, API/caché y prueba de
integración HTTP real Waitress → render → SDK simulado con cierre limpio.
Prueba Node de rotación aprobada; dependencias sin conflictos.
La validación de Compose comprueba estructura, no ejecuta redes ni contenedores.

**Pendiente**: build Python 3.12 Linux, sonda ABI contra headers oficiales,
licencia concreta y carga libndi real, permisos D-Bus/Avahi y volúmenes, discovery,
recepción/alpha/FPS en vMix y Studio Monitor, medición de recursos y aislamiento
de Internet. La prueba del loader Linux en Windows es simulada; no se presenta
como una transmisión Linux validada. No hay SDK/.so en esta carpeta de desarrollo.

En ventana de pruebas autorizada, comprobar fallo de API conservando paneles,
reinicio del servicio conservando titulares y recuperación automática del
supervisor ante un hijo bloqueado. No provocar esos fallos en la web de producción
ni detener otros contenedores. Los casos de fallo se cubren aquí con simulaciones.

## Referencias oficiales consultadas

- [SDK y descarga](https://ndi.video/for-developers/ndi-sdk/)
- [Licencia](https://docs.ndi.video/all/developing-with-ndi/sdk/licensing)
- [Plataformas y Avahi](https://docs.ndi.video/all/developing-with-ndi/sdk/platform-considerations)
- [Frames y BGRA](https://docs.ndi.video/all/developing-with-ndi/sdk/frame-types)
- [Envío, clock y timecode](https://docs.ndi.video/all/developing-with-ndi/sdk/ndi-send)
- [Configuración y selección de adaptadores](https://docs.ndi.video/all/developing-with-ndi/sdk/configuration-files)
- [Puertos](https://docs.ndi.video/all/getting-started/white-paper/ndi-related-network-ports)
- [Docker host networking](https://docs.docker.com/engine/network/drivers/host/)
- [Publicación localhost y versiones](https://docs.docker.com/engine/network/port-publishing/)
