# NOTICIAS LATERAL – EL DEBER

Web/API y emisor NDI® preparados para dos servicios en un único Ubuntu administrado
por Dokploy. Windows sigue soportado para desarrollo local y recepción de prueba.
NDI® is a registered trademark of Vizrt NDI AB. [Información NDI](https://ndi.video/).

La web ya funciona en `noticias.grupoeldeber-corp.com`. La nueva preparación Linux
no se ha desplegado. La guía completa, variables, licencia y pasos manuales están
en [DESPLIEGUE_NDI_LINUX.md](DESPLIEGUE_NDI_LINUX.md).

## Composición y noticias

Overlay transparente de 1920×1080, fotografía, categoría y fuentes Flama Condensed
originales. Las coordenadas internas se conservan. El lienzo web escala completo
según `min(ancho/1920, alto/1080)` desde la esquina superior izquierda y se ajusta
al redimensionar; en Full HD conserva escala 1. El render NDI es independiente.

- Rotación cada 15 segundos, actualización cada 180 segundos, hasta 14 noticias.
- La cola nueva se aplica en el próximo cambio sin reiniciar la vuelta.
- La web conserva su última cola en `/app/data/headlines.json`.
- NDI conserva los paneles en memoria si falla la API y guarda sus titulares en
  un volumen propio. Tras reiniciar necesita descargar las fotos de nuevo.
- Web y NDI no se sincronizan por fotograma. La cantidad real de titulares puede
  ser inferior a 14 si la portada no aporta suficientes noticias con foto.

## Dokploy / Ubuntu

Repositorio `luisferED/noticias-lateral`, rama `main`, archivo `compose.yaml`.
Actualizar el proyecto Dokploy existente, conservando su identidad y volumen web.
No usar Fresh Volumes. No cambiar el dominio ni la configuración Domains de web.

| Servicio | Red | Función |
| --- | --- | --- |
| web | dokploy-network | Web/API en 8095, ruta Traefik existente |
| ndi | host | ED_DEBER_TITULARES_ALPHA, 1920×1080 BGRA con alpha, 30 FPS |

NDI consulta `http://127.0.0.1:18095/api/headlines`: el Compose liga ese puerto web
solo a loopback. El puerto interno 8095 no se publica en las interfaces Ubuntu.
Si se cambia NDI_WEB_LOOPBACK_PORT, ajustar también HEADLINES_API_URL.
Los dos servicios usan usuario 10001:10001, reinicio automático y logs separados.
El supervisor NDI recupera bloqueos de envío; el healthcheck solo no reiniciaría
un contenedor unhealthy.

Dockerfile.ndi instala Python, NumPy, Pillow y clientes Avahi dentro de la imagen.
No descarga ni incluye el SDK/runtime propietario. Debe montarse libndi.so oficial
para la arquitectura real, con licencia aceptada, en una carpeta privada de Ubuntu.
También requiere el Avahi/D-Bus existente del host y acceso a la red de emisión.
No se instala ni se modifica nada en el servidor automáticamente.

**Antes de Deploy:** seguir la guía Linux para inspección de puertos, runtime,
ABI contra headers oficiales, permisos, aislamiento de Internet y pruebas reales.
La configuración y las pruebas simuladas no sustituyen la recepción en vMix/NDI
Studio Monitor. No hacer push o despliegue sin la revisión correspondiente.

## Windows para desarrollo local

1. Instalar Python 3.12 o superior x64 y ejecutar `instalar.bat`.
2. Revisar `.env`: ajustar HEADLINES_API_URL a la API local/remota que se utilizará.
   `.env.example` está orientado al Compose Linux y usa el puerto loopback 18095.
3. Para web local, ejecutar `iniciar.bat` y abrir `http://127.0.0.1:8095/`.
4. Instalar el runtime NDI Windows x64 por separado. Para emisor local configurar:

```dotenv
HEADLINES_API_URL=http://127.0.0.1:8095/api/headlines
NDI_SOURCE_NAME=ED_DEBER_TITULARES_ALPHA
NDI_FPS=30
ROTATE_SECONDS=15
REFRESH_SECONDS=180
MAX_ITEMS=14
```

Quitar NDI_LIBRARY_PATH=/opt/ndi/libndi.so si se copió desde el ejemplo Linux.
NDI_LIBRARY_PATH puede apuntar a la DLL local; se conserva NDI_DLL_PATH como
alternativa compatible y detección automática de NDI Tools 5/6.
Ejecutar `iniciar_ndi.bat`; detener con Ctrl+C. No mantener simultáneamente un
emisor Windows y otro Ubuntu con el mismo nombre durante las pruebas.

Con API remota, usar `https://noticias.grupoeldeber-corp.com/api/headlines` y
confiar en el certificado corporativo. Si la API falla, el emisor conserva su
última cola; ya no inicia un scraper local alternativo. Sigue necesitando acceso
al CDN para descargar fotos. Las variables del entorno tienen prioridad sobre .env.

## Pruebas y diagnóstico local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ndi.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_rotation.cjs
node tests/test_responsive.cjs
docker compose --env-file .env.example config --quiet
```

La prueba responsiva usa Chrome headless (o CHROME_PATH) y comprueba geometría y
transparencia en 1366×768, 1600×900, 1920×1080, 768×1366 y 2560×1440.
Las pruebas Python no necesitan SDK ni Internet; los envíos nativos son simulados.
Ver pruebas Linux pendientes y cómo validar headers/runtime en la guía dedicada.
`python ndi_sender.py --check-runtime` carga/inicializa el runtime sin crear fuente.
`python ndi_sender.py --preview` genera una imagen local con alpha desde la API.

- `/healthz`: estado del proceso web; 200 no garantiza noticias ni persistencia.
- `/api/config`: valores efectivos 15/180/14 y resolución 1920×1080.
- `/api/headlines`: 200 con cola; 503 sin fuente ni copia. Con copia antigua y
  fuente fallida devuelve 200 con `stale: true` y `ok: false`.
- `python ndi_status.py`: estado de frames completados; no valida recepción remota.

La web solo necesita requirements.txt; requisitos NDI separados en
requirements-ndi.txt. La extracción depende del HTML público de El Deber.
Los archivos de configuración privados, SDK, runtime, datos, ZIP y entornos
virtuales se excluyen de Git y de los contextos Docker. Gitignore no retira
archivos privados ya rastreados: revisar el diff antes de subir.

`tools/package.ps1` genera un paquete de fuentes en dist/, incluida la guía Linux,
con configuración de ejemplo y sin SDK/runtime ni .env privados.
