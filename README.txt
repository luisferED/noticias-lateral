PANTALLA DE TITULARES EL DEBER

1. Ejecutar iniciar.bat
2. Abrir en el navegador:
   http://127.0.0.1:8095

La pantalla obtiene titulares y fotos desde https://eldeber.com.bo/
Los titulares rotan cada 15 segundos y la portada se vuelve a consultar cada 3 minutos.
Se cargan hasta 14 noticias: una visible y hasta 13 en cola.
Primero ejecutar instalar.bat. Ver README.md para despliegue y configuracion.
El fondo queda transparente; solo se dibuja el panel derecho.

SALIDA 1920x1080 / NDI

- Ejecutar iniciar_ndi.bat para publicar una fuente NDI directa.
- Nombre de la fuente:
  NOMBRE-DEL-EQUIPO (ED_DEBER_TITULARES_ALPHA)
- Formato enviado:
  1920x1080 BGRA con alpha.
- El panel ocupa el espacio derecho de la plantilla:
  x=1556, y=0, ancho=335, alto=825.
- El area superior y=0 a y=77 queda transparente para la mosca/logo del programa.
- No se dibuja cabecera ni pie de actualizado/cantidad de titulares.
- No usar captura de pantalla ni Display Capture, porque vuelve opaco el fondo.
