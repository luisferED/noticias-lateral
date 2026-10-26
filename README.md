# NOTICIAS LATERAL – EL DEBER

Web/API en Ubuntu con Dokploy; transmisor NDI independiente en Windows.
Overlay transparente 1920×1080 con Flama Condensed. Se conservan imágenes,
fuentes, animaciones y lógica originales: rotación 15 s, consulta 180 s,
máximo 14 titulares con foto. La cola nueva se aplica en el siguiente cambio,
sin reiniciar la vuelta. La última cola se guarda en `DATA_DIR/headlines.json`.

## Estado de la preparación (26 de octubre de 2026)

- Servidor objetivo: `172.20.16.195`. TCP 22, 80, 443 y 3000 accesibles desde esta PC.
- HTTP 3000 responde 200 con título Dokploy. HTTP 80 sin Host de aplicación devuelve 404.
- Esto no verifica la versión de Docker/Dokploy, Traefik, la red ni otros proyectos:
  requiere ejecutar la inspección de abajo con una cuenta autorizada del servidor.
- `noticias.grupoeldeber-corp.com` no resolvió en el DNS consultado.
- Docker CLI existe en la PC de preparación, pero su motor no está disponible;
  el build Linux y la escritura real del volumen quedan pendientes.
- Esta carpeta no contiene `.git`. No se subió código ni se desplegó ni se eliminó nada.

Validación local realizada con Python 3.14 x64 en un `.venv` nuevo:
11 pruebas unittest aprobadas (API, caché persistente, recuperación sin fuente,
concurrencia, extracción y render NDI con alpha); prueba Node aprobada de
rotación 15 s, refresco 180 s y vuelta de 14 noticias; `pip check` sin conflictos.
Waitress respondió HTTP 200 a `/`, `/healthz` y `/api/config`, con valores
15/180/14. `docker compose config --quiet` pasó y su salida JSON confirmó red
externa, volumen y ausencia de puertos publicados. Docker CLI mostró advertencia
de acceso a su configuración de usuario, sin impedir validar Compose.
Hashes SHA-256 confirmaron sin cambios server.py, config.py, index.html,
ndi_sender.py, requirements.txt, imagen y las tres tipografías originales.
Quedan pendientes build/ejecución Linux Python 3.12, permisos reales del volumen,
enrutamiento Traefik, inventario de conflictos remoto y emisión NDI con runtime.
No se contó con una sesión autenticada del servidor para inspeccionarlo.

## 1. Inspección del servidor, antes del despliegue

Conectarse por SSH usando la cuenta Ubuntu autorizada (no se incluyen credenciales).
Ejecutar estas consultas de solo lectura; si no hay permisos, pedir al administrador
que las ejecute. No instalar Docker/Dokploy ni cambiar redes automáticamente.

```sh
cat /etc/os-release
command -v docker
docker version
docker compose version
docker info --format '{{.Swarm.LocalNodeState}}'
docker service ls
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker network inspect dokploy-network
docker volume ls
docker compose ls
ss -lnt
```

Confirmar Docker y Compose funcionales, Dokploy activo y Traefik activo en
`dokploy-network`. Inspeccionar el contenedor Traefik identificado con
`docker inspect <nombre-real-del-contenedor-traefik>` y comprobar sus redes,
versión de imagen, puertos y configuración. Revisar en el panel la versión de
Dokploy, los dominios de todos los proyectos y que el dominio propuesto no esté
asignado. No basta comprobar puertos abiertos para descartar conflictos.

El Compose mantiene `web`, no fija `container_name`, nombres globales de routers
ni nombre global del volumen. Dokploy debe usar un proyecto Compose único para
esta aplicación. El volumen `headlines-data` queda prefijado por ese proyecto.
No usar el mismo proyecto de otra aplicación ni cambiar su identificador después:
se podría seleccionar otro volumen. La única red compartida es `dokploy-network`.
No se publica 8095 en el host; Traefik reutiliza sus puertos 80/443 existentes.

## 2. Preparar GitHub sin subir automáticamente

Repositorio: `https://github.com/luisferED/noticias-lateral`, rama `main`.
Como esta carpeta no tiene historial Git, clonar el repositorio en otra carpeta,
revisar primero sus cambios e instrucciones y copiar allí los archivos revisados.
No reemplazar `.git`, `.env`, datos privados ni cambios ajenos.

```sh
git clone --branch main https://github.com/luisferED/noticias-lateral.git noticias-lateral-revision
cd noticias-lateral-revision
# Copiar aquí los archivos preparados; conservar assets originales.
git status --short
git diff --check
git diff
git status --short --ignored
git ls-files .env data '*.zip' '*.pem' '*.key'
```

`.gitignore` evita incorporar entornos, secretos, datos y archivos comprimidos;
no deja de rastrear archivos ya versionados. Si la última consulta muestra
archivos privados, revisarlos antes de subir. No publicar credenciales reales.
Tras revisión humana, crear el commit y subir a `main` mediante el flujo habitual
del repositorio. Estos pasos no se ejecutaron durante la preparación.

`.dockerignore` usa una lista permitida: únicamente Dockerfile, dependencias web,
server.py, config.py, index.html y assets. No entran `.env`, ZIP, Git, NDI,
pruebas, entornos ni la cola privada. Revisar que assets contenga solo recursos
públicos. No modificar las tipografías originales.

## 3. Dokploy

1. Seleccionar el servidor `172.20.16.195` ya verificado.
2. Crear un proyecto/aplicación **Docker Compose** con identificador único.
3. Conectar GitHub con acceso al repositorio, seleccionar
   `luisferED/noticias-lateral`, rama `main`, archivo `compose.yaml` en la raíz.
4. Desactivar despliegues automáticos durante la preparación. Usar el Dockerfile
   del repositorio; la imagen contiene únicamente la web/API y ejecuta Waitress.
5. Colocar en **Environment** exactamente:

```dotenv
ROTATE_SECONDS=15
REFRESH_SECONDS=180
MAX_ITEMS=14
```

`HOST=0.0.0.0`, `PORT=8095` y `DATA_DIR=/app/data` ya están fijados en Compose.
No hace falta duplicarlos en Environment: cambiar esas variables en el panel
no sustituye los valores literales del Compose. No colocar HEADLINES_API_URL,
NDI_SOURCE_NAME ni NDI_DLL_PATH en Dokploy. No se necesitan contraseñas de aplicación.

6. En **Domains**, añadir Host `noticias.grupoeldeber-corp.com`, servicio `web`,
   Container Port `8095`, ruta `/`, destino HTTP dentro del contenedor.
   Dokploy genera los routers/labels Traefik al desplegar. El Compose declara
   explícitamente la red externa y `traefik.docker.network=dokploy-network`.
   No agregar routers manuales duplicados ni publicar 8095.
7. Configurar DNS/TLS como se indica abajo. Mantener pendiente Deploy hasta
   aprobar la inspección y las pruebas de imagen.
8. Cuando se autorice desplegar: lanzar Deploy y revisar estado, healthcheck y logs.
   Los cambios de Domains en Compose requieren otro despliegue.

Referencias oficiales:
- https://docs.dokploy.com/docs/core/docker-compose/domains
- https://docs.dokploy.com/docs/core/troubleshooting/domains

## 4. DNS y HTTPS

`172.20.16.195` es una dirección privada. Para uso LAN/VPN, crear en el DNS interno
un registro A `noticias.grupoeldeber-corp.com → 172.20.16.195`. Todos los clientes,
incluida la PC NDI, deben resolverlo y tener ruta hacia esa IP.
Para acceso público, el A debe apuntar a la IP pública/NAT real autorizada y los
puertos 80/443 deben llegar a Traefik. No publicar la IP privada como solución
para acceso desde Internet. No modificar registros de otras aplicaciones.

Habilitar HTTPS en Domains cuando se tenga un método de certificado válido.
Let's Encrypt con desafío HTTP requiere DNS público y acceso externo a 80;
para un servicio exclusivamente interno, usar DNS challenge soportado por la
instalación o certificado corporativo confiable. No desactivar la validación TLS.

Antes de DNS se puede comprobar la ruta HTTP mediante Host:

```sh
curl --resolve noticias.grupoeldeber-corp.com:80:172.20.16.195 http://noticias.grupoeldeber-corp.com/healthz
```

Ejecutar después de desplegar y con ruta HTTP configurada. Con HTTPS válido:

```sh
curl --resolve noticias.grupoeldeber-corp.com:443:172.20.16.195 https://noticias.grupoeldeber-corp.com/healthz
```

## 5. Persistencia, permisos y pruebas Linux

`headlines-data:/app/data` persiste la última lista. La imagen prepara `/app/data`
como propiedad UID/GID `10001:10001` y ejecuta ese usuario sin privilegios. Un
volumen nuevo vacío hereda ese directorio de la imagen. Un volumen existente
con otros propietarios debe inspeccionarse antes: no se cambia ni elimina aquí.
No sustituirlo por un bind mount sin preparar sus permisos. No ejecutar como root
para sortear errores de escritura. Mantener una única réplica con esta caché.

En una máquina con Docker Linux disponible, antes de autorizar producción:

```sh
docker compose config --quiet
docker build -t noticias-lateral:revision .
# Volumen de prueba NUEVO; no montar el de producción en esta prueba.
docker run --rm --network none --mount type=volume,source=noticias-lateral-revision-data,target=/app/data noticias-lateral:revision python -c "import os,pathlib; p=pathlib.Path('/app/data/revision-permisos.tmp'); assert os.getuid()==10001 and os.getgid()==10001; p.write_text('ok'); p.rename(p.with_suffix('.ok')); print('UID/GID y escritura/rename OK')"
```

La prueba crea un volumen de revisión y un archivo marcador; no elimina archivos
ni volúmenes. Elegir otro nombre si ese volumen ya existe. La aplicación también
necesita escribir/renombrar para guardar su cola de forma atómica.

Después de desplegar, usar la terminal del servicio o el directorio Compose real
administrado por Dokploy (no levantar otro proyecto Compose por accidente):

```sh
docker compose ps
docker compose logs --tail=100 web
docker compose exec -T web id
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8095/healthz').read().decode())"
docker compose exec -T web python -c "import os; from pathlib import Path; p=Path('/app/data/headlines.json'); print('directorio escribible:',os.access(p.parent,os.W_OK)); print('cola persistida:',p.exists()); print(p.stat() if p.exists() else 'consultar API primero')"
```

Verificar con `docker inspect <contenedor-web>`: usuario `10001:10001`, health
`healthy`, red `dokploy-network`, volumen en `/app/data`, sin HostPort para 8095,
y labels generados que dirijan el dominio a 8095. Confirmar que Traefik esté en
la misma red. Consultar la API para generar cola y comprobar el archivo.
Probar reinicio del servicio y conservación de la cola en una ventana autorizada.
No ejecutar `down -v`, `volume rm`, `prune` ni borrar datos para resolver errores.

## 6. PC Windows: NDI independiente

1. Instalar Python de 64 bits (3.12 o superior) y NDI Runtime de 64 bits.
2. Ejecutar `instalar.bat` para crear `.venv` e instalar `requirements-ndi.txt`.
3. En `.env` de esta PC colocar:

```dotenv
HEADLINES_API_URL=https://noticias.grupoeldeber-corp.com/api/headlines
NDI_SOURCE_NAME=ED_DEBER_TITULARES_ALPHA
ROTATE_SECONDS=15
REFRESH_SECONDS=180
MAX_ITEMS=14
```

Para pruebas LAN por HTTP, configurar el dominio HTTP en Dokploy y agregar
manualmente en el archivo hosts de Windows (con permisos de administrador)
`C:\Windows\System32\drivers\etc\hosts`:

```text
172.20.16.195 noticias.grupoeldeber-corp.com
```

Usar entonces `HEADLINES_API_URL=http://noticias.grupoeldeber-corp.com/api/headlines`.
Esto consulta el servidor 172.20.16.195 conservando el Host requerido por Traefik.
No usar `http://172.20.16.195:8095/api/headlines`: 8095 no está publicado.
Una URL con la IP sola tampoco coincide con el router del dominio. Con DNS
interno funcionando no hace falta la entrada hosts.

4. Probar `curl.exe -f https://noticias.grupoeldeber-corp.com/api/headlines`
   (HTTP si se está usando la ruta temporal).
5. Ejecutar únicamente `iniciar_ndi.bat`; no necesita `iniciar.bat` ni web local.
   La fuente es `ED_DEBER_TITULARES_ALPHA`, 1920×1080 BGRA con alpha a 30 fps.
6. Comprobar en el receptor NDI la fuente, transparencia y transiciones; detener
   con Ctrl+C. El nombre puede incluir el equipo como prefijo.

Si no se detecta el runtime, configurar `NDI_DLL_PATH` con la DLL x64 local real.
El runtime no se distribuye. NDI se anuncia desde Windows en la red de emisión;
no se instala ni se ejecuta dentro del contenedor Linux.
El comportamiento original conserva un respaldo: si la API remota falla, NDI
intenta obtener noticias directamente mediante server.py en Windows. La PC
necesita acceso HTTPS a El Deber y su CDN para ese respaldo y las fotografías.
Web y NDI rotan independientemente; no están sincronizados por fotograma.

## 7. Desarrollo y comprobaciones

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ndi.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_rotation.cjs
```

Para web local: `iniciar.bat`, abrir `http://127.0.0.1:8095/`.
Para Linux sin Docker: instalar `requirements.txt` y ejecutar `python server.py`.
La web no depende de NumPy, Pillow ni NDI Runtime; estas dependencias quedan en
`requirements-ndi.txt` para Windows. Los requisitos directos tienen versiones fijas.

- `/healthz`: 200 indica proceso disponible, incluso sin noticias. `source_ok`
  puede ser null antes de la primera consulta; no valida permisos ni fuente.
- `/api/config`: debe devolver 15, 180, 14 y resolución 1920×1080.
- `/api/headlines`: 200 con noticias; 503 sin fuente ni copia. Con última cola y
  fuente fallida devuelve 200 con `stale: true` y `ok: false`.
- Abrir `/` y verificar fuentes/fotos, transparencia y rotación completa de hasta
  14 titulares; el refresco no debe interrumpir el orden.
- `python ndi_sender.py --preview` genera PNG con alpha (requiere acceso a fotos).

El servidor consulta la portada bajo demanda con caché de 180 s; web y NDI
mantienen la actualización periódica al consumirla. La extracción depende del
HTML de El Deber; puede haber menos de 14 noticias válidas con foto.

`tools/package.ps1` genera un ZIP en `dist/` con fuentes y configuración de
ejemplo, excluyendo entorno, datos y `.env`. El ZIP anterior de la raíz se
conserva, pero no se incluye en Git ni en la imagen Docker.
