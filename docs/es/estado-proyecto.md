# Estado técnico del proyecto — Campo Digital LiDAR

## Objetivo

El objetivo del PoC es determinar si una nube de puntos LiDAR obtenida en el flujo operativo de Campo Digital puede utilizarse para producir una medición de madera reproducible y suficientemente cercana a la medición que Campo Digital considera correcta.

El proyecto todavía no está en la etapa de afirmar una precisión final en m³.

Actualmente estamos construyendo primero una base técnica que permita saber exactamente qué información contiene la nube, qué parte de esa información es confiable y qué geometría de la ruma puede observarse realmente.

---

## Problema principal

La cubicación no debe modelarse simplemente como:

~~~text
nube de puntos
    ↓
m³
~~~

El problema real tiene varias capas:

~~~text
ruma física
    ↓
captura del sensor
    ↓
registro / reconstrucción
    ↓
nube exportada
    ↓
limpieza y selección de la ruma
    ↓
geometría visible
    ↓
geometría no visible o inferida
    ↓
medición geométrica
    ↓
regla de cubicación de Campo Digital
    ↓
resultado reportado
~~~

Cada capa puede introducir error.

---

## Dataset actual

Archivo analizado:

`v01_MG_23jun2026.las`

### Hechos confirmados

- 9.718.909 puntos.
- LAS versión 1.2.
- Point Format 3.
- Contiene RGB.
- Contiene intensidad.
- Contiene GPS Time.
- Todos los puntos aparecen clasificados como clase 1.
- No existe un CRS explícito en el archivo.
- El archivo fue generado o convertido mediante una herramienta identificada como `txt2las`.
- No se ha confirmado todavía qué sensor produjo originalmente esta nube.

---

## Hallazgo: los límites del encabezado LAS no son confiables

El encabezado del LAS declara una extensión espacial considerablemente mayor que la geometría realmente presente en los puntos.

Extensión observada directamente desde los puntos:

~~~text
X: ~200,242 unidades de origen
Y: ~80,756 unidades de origen
Z: ~38,401 unidades de origen
~~~

La implementación ahora calcula los límites reales desde los puntos y conserva los límites del encabezado únicamente para auditoría.

### Importancia

Un algoritmo que utilizara directamente los límites del encabezado podría partir de una representación geométrica incorrecta antes de comenzar la medición.

---

## Hallazgo: la escala numérica del LAS no representa precisión real

La escala almacenada en el archivo es:

~~~text
0.0001
~~~

Esto corresponde a resolución de almacenamiento de coordenadas.

No demuestra automáticamente precisión del sensor ni precisión de la cubicación.

Debe distinguirse entre:

~~~text
resolución numérica del LAS
!=
precisión del sensor
!=
precisión de la nube registrada
!=
precisión de la medición geométrica
!=
precisión final de la cubicación
~~~

---

## Hallazgo: todavía no podemos declarar metros ni m³

Las coordenadas parecen compatibles con un sistema proyectado, pero el LAS no declara CRS.

Por esta razón actualmente utilizamos el concepto:

~~~text
unidades de origen
~~~

y no asumimos automáticamente metros.

Hasta confirmar las unidades no corresponde presentar resultados volumétricos como m³.

---

## Hallazgo: existe una estructura temporal muy clara

El archivo conserva GPS Time.

El orden temporal de los puntos es monotónico:

~~~text
saltos hacia atrás en GPS Time: 0
~~~

Esto indica que una estructura significativa del proceso de captura o exportación sobrevivió dentro del LAS.

---

## Hallazgo: estructura de retornos altamente regular

Se identificaron:

~~~text
5.609.224 grupos de timestamp
~~~

Distribución:

~~~text
1 punto: 1.499.539 grupos
2 puntos: 4.109.685 grupos
máximo: 2 puntos por timestamp
~~~

Todos los grupos con dos registros siguen exactamente:

~~~text
Retorno 1
    ↓
Retorno 2
~~~

Resultado:

~~~text
1 -> 2 : 4.109.685
2 -> 1 : 0
1 -> 1 : 0
2 -> 2 : 0
~~~

Esto demuestra una relación estructural fuerte entre GPS Time y Return Number.

### Limitación

Todavía no se puede afirmar que cada par corresponda necesariamente al primer y segundo eco físico del mismo pulso láser.

Necesitamos confirmar el sensor y el proceso de exportación.

---

## Hallazgo: existen pares R1/R2 con separación espacial muy grande

En los 4.109.685 grupos exactos R1/R2:

~~~text
separación 3D mínima: 0
separación 3D media: ~0,271 unidades de origen
separación 3D máxima: ~87,941 unidades de origen
~~~

Como ningún timestamp contiene más de dos registros, la separación máxima no se explica por haber mezclado accidentalmente grupos de tres o más puntos.

Esto requiere investigación adicional.

No corresponde interpretar todavía todos los pares R1/R2 como superficies cercanas de una misma pieza de madera.

---

## Hipótesis actual para atacar la cubicación

En CloudCompare se observa una gran cara visible de la ruma donde aparecen los extremos circulares o elípticos de numerosos rollizos.

La hipótesis de trabajo es utilizar esta cara como primera fuente de geometría directamente medible.

Flujo esperado:

~~~text
nube completa
    ↓
ROI reproducible de la ruma
    ↓
orientación local de la cara
    ↓
extracción de la cara visible
    ↓
detección de extremos de rollizos
    ↓
estimación de diámetros
    ↓
conteo + control de calidad
    ↓
información de largo/profundidad
    ↓
geometría de madera
    ↓
regla de cubicación Campo Digital
~~~

---

## Limitación fundamental: geometría no visible

Un extremo circular visible permite estimar el diámetro de un rollizo.

Sin embargo, no necesariamente permite conocer su largo oculto.

Para un cilindro ideal:

~~~text
V = pi * (d / 2)^2 * L
~~~

La cara frontal ayuda con `d`.

La variable `L` debe obtenerse mediante información adicional si no está visible.

Por ejemplo:

- largo estándar conocido;
- escaneo del lado opuesto;
- geometría lateral;
- profundidad independiente de la ruma;
- metadatos operacionales;
- regla utilizada actualmente por Campo Digital.

Esta es una limitación de observabilidad, no simplemente un problema de mejorar el algoritmo.

---

## La definición de "volumen correcto" todavía está abierta

Todavía necesitamos confirmar si Campo Digital requiere:

- volumen exterior de la ruma;
- volumen sólido de madera;
- suma de volumen de rollizos individuales;
- volumen estéreo;
- área transversal multiplicada por profundidad;
- otra regla forestal/comercial.

Estos resultados no son equivalentes.

---

## Ground truth pendiente

Todavía no contamos con una medición de referencia confirmada para exactamente la misma ruma y el mismo ROI.

Antes de calcular error necesitamos:

~~~text
misma ruma
mismo tramo / ROI
valor de referencia
unidad
método
operador/procedimiento
~~~

Una medición de LiDAR360 o Pix4D tampoco debe asumirse automáticamente como verdad perfecta; primero necesitamos conocer cómo fue obtenida.

---

## Lo que ya está demostrado

Actualmente podemos:

- leer la nube real completa;
- procesar 9,7 millones de puntos reproduciblemente;
- trabajar en streaming;
- proteger los datos reales fuera de Git;
- detectar límites LAS inconsistentes;
- conservar la ausencia de CRS sin inventarlo;
- analizar GPS Time;
- reconstruir grupos de timestamps;
- caracterizar los retornos;
- detectar anomalías del proceso de adquisición/exportación.

---

## Lo que todavía NO está demostrado

Todavía no tenemos:

- sensor exacto confirmado;
- CRS confirmado;
- unidades lineales confirmadas;
- interpretación física confirmada de R1/R2;
- ROI automático de la ruma;
- detección automática de rollizos;
- diámetros validados;
- conteo validado;
- largo/profundidad validado;
- volumen geométrico validado;
- regla comercial de cubicación confirmada;
- ground truth para esta misma ruma;
- porcentaje de error final;
- precisión validada en m³.

---

## Próxima fase

La prioridad principal pasa ahora a:

### Fase C — ROI reproducible de la ruma

Objetivo:

> aislar de manera determinista la cara visible de madera dentro de la nube completa.

CloudCompare seguirá utilizándose para inspección visual.

La selección final debe poder reproducirse desde configuración o código.

Después:

### Fase D — geometría de la cara y extremos de rollizos

El primer experimento directo sobre el problema forestal será determinar si podemos identificar de manera estable los extremos circulares/elípticos visibles y estimar sus diámetros.

Ese será el primer paso que conecta directamente la nube de puntos con la futura cubicación.

<!-- DOC_NAV_START -->

---

### Navegación de documentación

[README del proyecto](../../README.md) · [Índice de documentación](../README.md) · [Hallazgos](../findings/cubicacion_accuracy_problem.md) · [Experimentos](../experiments) · [Decisiones](../decisions) · [Documentación en español](README.md) · [Preguntas Campo Digital](preguntas-campo-digital.md)

<!-- DOC_NAV_END -->


---

## Estado actual: ruma aislada y geometría frontal reproducible

Desde el análisis forense inicial se avanzó hasta una primera ruta geométrica reproducible sobre la ruma real.

### ROI automática de la ruma

Se construyó una selección automática de la estructura principal de madera.

Resultado actual:

~~~text
puntos ROI candidata:
4.074.894

puntos ruma automática:
1.342.183
~~~

La segmentación automática fue comparada geométricamente con una referencia manual realizada en CloudCompare.

A una tolerancia geométrica de 0,10 unidades de origen:

~~~text
precision-like: 95,57%
recall-like:    85,71%
F1-like:        90,37%
~~~

Estas cifras representan cercanía geométrica entre selecciones.

No representan todavía precisión final de cubicación.

---

## Hallazgo: no se observa una segunda pared coherente de madera

Se investigó si la nube contenía una segunda cara opuesta de la ruma que permitiera obtener directamente su profundidad.

Se analizaron:

- perfiles transversales;
- slices longitudinales;
- limpieza de suelo;
- extensión vertical por posición transversal;
- vistas desde ambos lados de la nube.

Existían grupos importantes de puntos aproximadamente a:

~~~text
T ≈ -5 a -6 unidades de origen
~~~

respecto de la cara visible.

Sin embargo, la evidencia muestra que esa estructura corresponde principalmente a suelo, camino y otra geometría del entorno.

No apareció una segunda pared vertical de madera persistente.

### Consecuencia

Actualmente no corresponde utilizar esa separación como profundidad de la ruma.

Tampoco corresponde cerrar artificialmente la nube con una superficie posterior y llamar al resultado volumen físico medido.

La profundidad debe mantenerse como una variable explícita hasta obtener evidencia adicional.

---

## Detección de extremos visibles de rollizos

También se desarrolló una proyección frontal reproducible de la ruma.

La proyección conserva la relación exacta entre:

~~~text
pixel 2D
    ↕
puntos originales del LAS
~~~

Esto permite detectar una estructura en imagen y posteriormente recuperar sus puntos 3D originales.

Se probaron detectores clásicos de extremos de rollizos.

El mejor detector balanceado actual utiliza votación radial basada en gradientes.

En una región exhaustivamente etiquetada con 70 extremos visibles:

~~~text
tolerancia: 8 px

precision: 66,7%
recall:    65,7%
F1:        66,2%
~~~

Una variante orientada a mayor recall obtuvo:

~~~text
precision: 61,7%
recall:    71,4%
F1:        66,2%
~~~

### Decisión

La detección individual de rollizos queda conservada como capacidad secundaria.

No continuará siendo optimizada por ahora porque todavía no resuelve la dimensión oculta necesaria para cubicación.

---

## Ruta principal actual: sección frontal de la ruma

La cara de madera directamente observable sí permite obtener una sección longitudinal/vertical.

La medición reproducible actual entrega:

~~~text
puntos utilizados:
1.342.183

largo longitudinal robusto:
61,361422 unidades de origen

altura mediana:
3,688422 unidades de origen

altura máxima:
4,632758 unidades de origen

área frontal:
217,176317 unidades-de-origen²
~~~

Una integración trapezoidal independiente entrega:

~~~text
216,434772 unidades-de-origen²
~~~

lo que confirma que la integración numérica es consistente.

---

## Sensibilidad del área frontal

Se repitió la medición usando:

~~~text
80
120
160
240
~~~

divisiones longitudinales y tres definiciones distintas de borde vertical.

El número de divisiones modifica el área aproximadamente un 1% o menos para una misma definición de borde.

El mayor efecto proviene de decidir cuánto del extremo superior e inferior de la nube corresponde a la ruma.

Rango observado:

~~~text
mínimo:
202,767 unidades-de-origen²

central:
~217,467 unidades-de-origen²

máximo:
224,646 unidades-de-origen²
~~~

El rango total equivale aproximadamente a:

~~~text
10,06%
~~~

del valor mediano.

Esto representa sensibilidad del método de extracción.

No representa todavía incertidumbre física total.

---

## Modelo volumétrico actual

Como la profundidad no está observada de manera confiable, el modelo actualmente permitido es:

~~~text
V(d) = A_frontal * d
~~~

donde:

~~~text
A_frontal = geometría medida directamente
d         = profundidad explícita o validada externamente
~~~

La profundidad no se estima automáticamente desde esta nube.

Ejemplo con:

~~~text
d = 5 unidades de origen
~~~

usando la configuración base:

~~~text
V = 1085,881584 unidades-de-origen³
~~~

Esto sigue siendo una medición geométrica por extrusión.

No debe presentarse todavía como m³ ni como cubicación comercial validada.

---

## Implementación actual

La medición frontal ya no existe solamente como experimento.

Se implementó como código reutilizable:

~~~text
src/lidar_volume/front_cross_section.py
~~~

y está disponible mediante:

~~~bash
uv run lidar volume ARCHIVO.las
~~~

Sin profundidad explícita, el comando entrega solamente geometría observable.

Con:

~~~bash
uv run lidar volume ARCHIVO.las --depth D
~~~

también calcula:

~~~text
A_frontal * D
~~~

La implementación reutilizable reproduce el experimento original con una diferencia relativa de aproximadamente:

~~~text
0,000146%
~~~

---

## Información que todavía necesitamos de Campo Digital

Para avanzar desde geometría reproducible hacia validación real de cubicación necesitamos:

1. confirmar qué sensor produjo este LAS;
2. confirmar CRS y unidades físicas;
3. obtener la ruma/ROI exacta usada por Campo Digital;
4. obtener el volumen de referencia de Pix4D o LiDAR360 para esa misma ruma;
5. conocer el largo/profundidad utilizado operacionalmente;
6. saber qué representa exactamente el volumen final:
   - volumen geométrico de envolvente;
   - volumen sólido de madera;
   - volumen con correcciones;
   - otra regla comercial.

Hasta contar con esa referencia no corresponde afirmar precisión final en m³.
