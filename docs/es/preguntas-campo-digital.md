# Preguntas abiertas para Campo Digital

Este documento registra información que debe ser confirmada por Javier o el equipo de Campo Digital.

No se deben completar respuestas mediante inferencia.

| Estado | Pregunta | Por qué importa | Respuesta confirmada |
|---|---|---|---|
| Abierta | ¿Qué sensor produjo exactamente `v01_MG_23jun2026.las`? | Permite interpretar adquisición, retornos y precisión | — |
| Abierta | ¿Corresponde a DJI L2, XGRIDS K2, GEOSUN GS100G u otro sensor? | Define hardware y pipeline de origen | — |
| Abierta | ¿Cuál es el CRS del archivo? | Necesario para interpretar coordenadas | — |
| Abierta | ¿Cuáles son las unidades lineales? | Necesario antes de declarar metros o m³ | — |
| Abierta | ¿Qué software procesó originalmente la captura? | Ayuda a interpretar la nube registrada | — |
| Abierta | ¿Cuál fue la secuencia exacta de exportación hasta llegar al LAS? | El archivo indica `txt2las`; necesitamos conocer qué ocurrió antes | — |
| Abierta | ¿La nube ya viene completamente registrada / SLAM-resuelta? | Define si debemos trabajar solo geometría o también reconstrucción | — |
| Abierta | ¿Cuál es la medición de referencia para esta misma ruma? | Necesaria para calcular error | — |
| Abierta | ¿La referencia fue obtenida con LiDAR360, Pix4D, método manual u otro? | Define la calidad y significado del ground truth | — |
| Abierta | ¿Qué tramo exacto de la nube corresponde a esa medición? | Necesitamos comparar el mismo ROI | — |
| Abierta | ¿Qué significa exactamente "cubicación" en su flujo comercial? | Define la variable objetivo | — |
| Abierta | ¿Buscan volumen sólido, volumen de ruma, estéreo, suma de trozas u otra fórmula? | Los resultados son distintos | — |
| Abierta | ¿Los rollizos tienen un largo estándar o largos variables? | La cara frontal no determina por sí sola el volumen total | — |
| Abierta | ¿Normalmente se escanea una sola cara o ambos lados de la ruma? | Determina qué geometría es observable | — |
| Abierta | ¿Se mide la profundidad/largo de la ruma independientemente? | Puede resolver la geometría oculta | — |
| Abierta | ¿Qué significa exactamente el objetivo de 1–2 cm? | Puede referirse a posición, diámetro, repetibilidad u otra métrica | — |
| Abierta | ¿Qué error final de cubicación sería comercialmente aceptable? | Define criterio de aceptación del PoC | — |
| Abierta | ¿Qué repetibilidad esperan entre dos operadores diferentes? | Permite evaluar robustez operacional | — |
| Abierta | ¿Existe una función específica para los QR/referencias cada ~20 m? | Puede afectar segmentación, escala o corrección de trayectoria | — |

## Regla de actualización

Cuando una respuesta sea entregada explícitamente por Campo Digital:

1. registrar la respuesta;
2. cambiar `Estado` a `Resuelta`;
3. registrar la fuente o contexto si es relevante;
4. actualizar la documentación técnica afectada;
5. no borrar la pregunta original, porque forma parte de la trazabilidad del proyecto.
