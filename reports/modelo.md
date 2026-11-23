# Modelo de gravedad de los siniestros con victimas (SI7009)

Este informe recorre los criterios 1 a 6 de la rubrica de Aprendizaje
Automatico. Todos los numeros salen de `data/gold/modelos/metricas.json`
(version `runt-2026-11-21-68160f32`, la misma que sirve la API en AWS) y de las tablas de `data/gold/modelos`,
y se reproducen con `python -m src.pipeline`. Las semillas estan fijas; que
dos corridas den un `metricas.json` identico byte a byte se comprobo con la
version anterior del flujo, antes de repartir las cargas masivas.

## 1. Formulacion del problema

- **Decision que apoya.** Priorizar controles, campañas y revisiones hacia
  los perfiles de vehiculo y los contextos con mas riesgo de que un siniestro
  con victimas termine con muertos, y comparar la letalidad observada de cada
  municipio con la esperada para detectar municipios fuera de lo normal.
- **Tarea de ML.** Clasificacion binaria supervisada con salida de
  probabilidad.
- **Unidad de observacion.** Un vehiculo involucrado en un siniestro con
  victimas (una fila del RUNT, identificada por `id_registro`). La fuente no
  trae dia, hora ni direccion, asi que no se sabe que vehiculos estuvieron
  en el mismo siniestro.
- **Objetivo.** `con_muertos` = 1 si el siniestro fue CON MUERTOS, 0 si fue
  CON HERIDOS. Prevalencia 5.3% en todo el periodo.
- **Variables.** Del vehiculo: `tipo_grupo`, `marca_grupo`, `modelo`, `edad`
  al momento del siniestro. Del contexto: `mes`, `departamento`, `autoridad`
  de transito.
- **Supuestos y restricciones.** La gravedad es del siniestro, no del
  vehiculo: el modelo no dice que vehiculo causo la muerte. Encuentra
  asociaciones, no causas. Los meses con cobertura anomala y los registros
  de cargas masivas con fecha reubicada se dejan fuera del entrenamiento.
  2025-2026 tiene cobertura cambiada y se evalua aparte.
- **Por que no se usa el municipio como variable.** El modelo debe servir en
  municipios que no vio, y la validacion agrupada por municipio deja siempre
  el municipio de prueba fuera del entrenamiento: un identificador de
  municipio no aportaria nada en prueba y solo inflaria el ajuste. La
  autoridad si entra (lo pide la base del proyecto), pero en los municipios
  no vistos su secretaria tambien es nueva; solo la autoridad nacional, que
  esta en 645 municipios, se transfiere.

## 2. EDA e ingenieria de caracteristicas

El detalle esta en [eda.md](eda.md). Los hallazgos que cambiaron el
preprocesamiento:

| Hallazgo | Decision en el pipeline |
|---|---|
| EDAD_VEHICULO es la edad a la fecha de publicacion (difiere de la edad al siniestro en 5 años en 2022 y 1 en 2026) | `edad = año del siniestro - modelo`, minimo 0 |
| 381 marcas, muchas con pocas filas | `marca_grupo`: marcas con menos de 200 filas van a OTRAS (64 marcas + OTRAS) |
| 31 tipos, 20 con menos de 1,000 filas | `tipo_grupo`: tipos con menos de 1,000 filas van a OTRO |
| 237 autoridades, muchas pequeñas | El codificador agrupa las categorias con menos de 100 filas (`min_frequency`) |
| 83 modelos imposibles | Se marcan y quedan sin edad; los arboles tratan el vacio como faltante y la logistica imputa la mediana |
| Cargas masivas: reportes tardios subidos con una sola fecha (64 municipio-meses de 31 municipios; Medellin en julio de 2024 publica 22,667 registros) | El mes conserva su mediana y el exceso se reparte entre los meses anteriores del municipio: 21,230 filas con `fecha_imputada = 1` y el mes publicado en `periodo_original` |
| Caidas de reporte y meses que siguen anomalos despues del reparto | `cobertura_anomala`: esas filas y las de fecha reubicada no entran al entrenamiento (23,752 filas, 5.3%; 21,399 en 2022-2024) |
| 159,399 filas identicas a otra en la fuente | Se conservan: dos vehiculos iguales en el mismo mes y municipio son reales. `id_registro` (RUNT-000001 a RUNT-450335, por la posicion en el CSV) distingue cada fila |

Todo el preprocesamiento (codificacion, imputacion, escalado) va dentro de un
`Pipeline` de scikit-learn que se ajusta solo con los datos de entrenamiento
de cada pliegue, asi que no hay fuga por preprocesar antes de dividir.

## 3. Entrenamiento, validacion y seleccion

**Esquema.** Datos de 2022-2024 sin meses anomalos ni filas con fecha
reubicada: 327,068 filas, prevalencia 4.80%.

1. **Busqueda de hiperparametros** con `GridSearchCV` de scikit-learn,
   `GroupKFold` k=5 por municipio y PR-AUC como puntaje, sobre una muestra de
   120,000 filas para que el flujo corra en pocos minutos. La base del
   proyecto planeaba optuna; Glue solo ofrece scikit-learn, asi que se usa una
   rejilla pequeña y sistematica (desviacion de la base del proyecto).
   - Regresion logistica: C en {0.01, 0.1, 1}. Mejor C = 0.01 (PR-AUC 0.1475),
     la regularizacion mas fuerte de la rejilla.
   - Gradient boosting: tasa de aprendizaje {0.05, 0.1} x hojas {15, 31, 63}
     x regularizacion L2 {0, 1}, 12 combinaciones. Mejor: 0.1, 31 hojas, L2 = 1
     (PR-AUC 0.1607). Gana el tamaño de arbol intermedio con regularizacion,
     coherente con una señal debil.
   - Bosque aleatorio: configuracion fija (60 arboles, profundidad 14, hoja
     minima 20), sin busqueda para limitar el tiempo.
2. **Seleccion** con `GroupKFold` k=5 por municipio sobre las 327,068 filas.
   Los municipios de validacion nunca se ven al entrenar, y como cada
   siniestro tiene un solo municipio, los vehiculos de un mismo siniestro no
   quedan repartidos entre entrenamiento y prueba.
3. **Prueba temporal** con el test intacto hasta el final: entrenar con
   2022-2023 (226,539 filas) y probar con 2024 (100,529 filas, prevalencia
   5.20%). Cada modelo se calibra con regresion isotonica (3 pliegues).
4. **2025-2026** se evalua aparte con el modelo final (entrenado con
   2022-2024), marcado como periodo con cobertura cambiada.

Todos los modelos usan pesos por clase (`class_weight` balanceado). No se
probo la submuestra de la clase mayoritaria que mencionaba la base del
proyecto.

**Resultados.**

| Modelo | PR-AUC agrupada (media +- desv.) | ROC-AUC agrupada | PR-AUC 2024 | ROC-AUC 2024 | Brier 2024 |
|---|---|---|---|---|---|
| Prevalencia (linea base) | 0.052 +- 0.029 | 0.500 | 0.052 | 0.500 | 0.0493 |
| Regresion logistica (linea base) | 0.143 +- 0.077 | 0.693 | 0.221 | 0.825 | 0.0440 |
| Bosque aleatorio (ensamble) | 0.156 +- 0.081 | 0.695 | 0.215 | 0.817 | 0.0444 |
| **Gradient boosting (ensamble)** | **0.162 +- 0.083** | **0.704** | **0.232** | **0.825** | **0.0438** |

Gana el gradient boosting por PR-AUC agrupada, y tambien es el mejor en la
prueba temporal por PR-AUC y Brier; en ROC-AUC 2024 empata con la regresion
logistica (0.8247 frente a 0.8246). La ventaja sobre la regresion logistica
es pequeña (0.019 en PR-AUC agrupada, 0.011 en 2024): casi toda la señal es
aditiva.

**Sorpresa: la validacion por municipio es mucho mas dura que la temporal.**
En 2024 el modelo ya conoce las autoridades de cada municipio y logra 0.232
de PR-AUC; en municipios nuevos baja a 0.162. Ademas varia mucho entre
pliegues (0.034, 0.122, 0.231, 0.211 y 0.214): el pliegue de 0.034 es
Medellin solo, con una prevalencia de 0.7%, porque reporta muchos siniestros
con heridos y muy pocos con muertos.

## 4. Metricas y diagnostico

**Metrica principal: PR-AUC.** Con 5.3% de positivos la exactitud no sirve
(decir siempre "con heridos" da 94.7%), y la ROC-AUC se ve bien aunque el
modelo genere muchas falsas alarmas, porque los negativos son tantos. La
PR-AUC mide que tan bien se ordenan los casos con muertos arriba y su valor
de referencia es la prevalencia: 0.052, tanto en la media de los pliegues
como en 2024. El modelo la multiplica por 3.1 en municipios nuevos (0.162) y
por 4.5 en 2024 (0.232). La base del proyecto esperaba una PR-AUC que
superara "ampliamente" 0.053 (la prevalencia de todo el periodo): la supera,
pero el valor absoluto es modesto. La señal del vehiculo es debil, como
advertia la base del proyecto.

**Calibracion.** Los pesos por clase inflan las probabilidades: sin calibrar,
el Brier del gradient boosting en 2024 es 0.1695, peor que predecir siempre
la prevalencia (0.0493). Con calibracion isotonica baja a 0.0438. Tabla de
confiabilidad en 2024 (deciles de probabilidad):

| Decil | Probabilidad media | Tasa observada |
|---|---|---|
| 1 | 0.005 | 0.005 |
| 3 | 0.011 | 0.009 |
| 5 | 0.023 | 0.019 |
| 7 | 0.034 | 0.039 |
| 9 | 0.100 | 0.106 |
| 10 | 0.242 | 0.245 |

Las probabilidades calibradas se pueden leer como frecuencias, y eso es lo
que permite fijar el umbral por costos y calcular la letalidad esperada.

**Sesgo y varianza.** En la validacion agrupada el gradient boosting tiene
PR-AUC de 0.259 en entrenamiento y 0.162 en validacion (logistica: 0.225 y
0.143). La curva de aprendizaje sobre la muestra de busqueda:

| Filas de entrenamiento | PR-AUC entrenamiento | PR-AUC validacion |
|---|---|---|
| 8,677 | 0.2979 | 0.1332 |
| 26,032 | 0.2838 | 0.1467 |
| 86,776 | 0.2552 | 0.1578 |

La brecha se cierra con mas datos y las dos curvas quedan bajas: domina el
sesgo (pocas variables, señal debil) mas que la varianza. Lo que queda de
brecha es sobre todo cambio entre municipios (reportan distinto), no
sobreajuste a filas. Mas datos del mismo tipo ayudarian poco; harian falta
variables nuevas (tipo de via, hora, victimas), que el CSV no trae.

**Errores por segmento (grupos de municipios, prediccion fuera de pliegue
2022-2024).**

| Segmento | Municipios | Filas | Prevalencia | PR-AUC | ROC-AUC | Sensibilidad | Precision |
|---|---|---|---|---|---|---|---|
| Grupo 1 (urbano) | 113 | 305,374 | 3.5% | 0.125 | 0.656 | 0.347 | 0.178 |
| Grupo 2 (carreteras) | 96 | 17,664 | 22.8% | 0.286 | 0.580 | 0.762 | 0.248 |
| Menos de 100 filas | 378 | 4,030 | 27.0% | 0.366 | 0.610 | 0.821 | 0.289 |
| Total | | 327,068 | 4.8% | 0.181 | 0.712 | 0.486 | 0.211 |

Dentro de cada grupo la ROC-AUC baja (0.58 a 0.66) frente a 0.71 en total:
buena parte de lo que el modelo sabe es distinguir contextos (ciudad frente a
carretera), y dentro de un mismo tipo de municipio discrimina poco. En los
municipios de carretera alerta el 70% de los registros, porque casi todos
superan el umbral.

**Importancia de variables** (permutacion sobre 30,000 filas de 2024, caida
de PR-AUC al desordenar cada variable; reemplaza a SHAP, que no esta en
Glue):

| Variable | Caida de PR-AUC |
|---|---|
| autoridad | 0.1526 |
| departamento | 0.0307 |
| tipo_grupo | 0.0176 |
| marca_grupo | 0.0048 |
| edad | 0.0015 |
| modelo | 0.0013 |
| mes | 0.0007 |

**Sorpresa: la autoridad pesa mucho mas que el vehiculo.** Los registros de
la policia de carreteras (autoridad nacional) tienen 22.3% con muertos y los
de las secretarias municipales 3.2%. Esto mezcla dos cosas: riesgo real (las
vias nacionales tienen mas velocidad) y sesgo de reporte (cada secretaria
reporta distinto; Medellin tiene 0.6% con muertos). El modelo no puede
separarlas. Del vehiculo, solo el tipo aporta (tractocamion, volqueta y
camion); marca, edad y modelo casi no suman una vez se conoce el tipo y el
contexto.

## 5. Metrica de negocio y utilidad

**Supuesto de costo.** No detectar un siniestro con muertos cuesta 10 veces
lo que una falsa alarma (una inspeccion o una campaña mal dirigida). Con
probabilidades calibradas el umbral que minimiza el costo esperado es
1 / (1 + 10) = **0.091**. En 2024 el mejor umbral de una rejilla de 0.02 a
0.49 (de 0.01 en 0.01) fue 0.09, con un costo de 0.3268 por registro; el
umbral teorico da 0.3260, incluso un poco menos, asi que la regla teorica
funciona.

Comparacion en 2024 (100,529 registros, 5,227 con muertos):

| Estrategia | Registros alertados | Casos con muertos detectados | Precision | Costo por registro |
|---|---|---|---|---|
| Sin modelo, no alertar | 0% | 0% | - | 0.520 |
| Sin modelo, alertar todo | 100% | 100% | 5.2% | 0.948 |
| Regla simple: carga o autoridad nacional | 12.8% | 51.4% | 20.8% | 0.354 |
| Alerta al azar del mismo tamaño que el modelo | 15.3% | 15.3% | 5.2% | |
| **Modelo (umbral 0.091)** | **15.3%** | **60.6%** | **20.6%** | **0.326** |

Con el modelo, revisar el 15% de los registros cubre el 61% de los casos con
muertos (3,170 de 5,227), casi cuatro veces lo que daria escoger al azar.
Frente a no hacer nada el costo baja 37%; frente a la regla simple, que ya
captura lo mas obvio, baja 8%. Es decir, la regla simple se lleva la mayor
parte del valor y el modelo agrega una mejora moderada, sobre todo porque
ordena los casos con probabilidades utiles en lugar de un si o no.

**Letalidad observada frente a esperada** (`gold/modelos/letalidad`,
predicciones fuera de pliegue 2022-2024, cada municipio predicho por un
modelo que no lo vio):

- Medellin: 0.5% observada frente a 3.3% esperada (razon 0.16). Lo mas
  probable es subregistro de muertos o sobrerregistro de heridos, no que sea
  seis veces mas seguro.
- Bogota: 3.6% frente a 1.6% (razon 2.2) y Soacha 15.7% frente a 4.2% (razon
  3.8), los municipios grandes con mas letalidad de la esperada.
- Urrao, Girardota, Sabaneta y Envigado tienen razones de 0.26 a 0.41: el
  patron de bajo registro de muertos se repite en otros municipios de
  Antioquia, sobre todo del area metropolitana de Medellin.

**Limitaciones y riesgos.** El modelo aprende la forma de reportar de cada
autoridad, no solo el riesgo. En 2025-2026 (cobertura cambiada) la PR-AUC es
0.271 y la ROC-AUC 0.804, pero la prevalencia sube a 7.8%, el Brier sube a
0.064 y el modelo alerta el 27% de los registros: la mezcla de quien reporta
cambio y la calibracion ya no es la de 2024. Antes de usarlo en un periodo
nuevo hay que recalibrar.

## 6. Caso aplicado

El modelo final (gradient boosting calibrado, `gradient_boosting.joblib`,
entrenado con 2022-2024) sobre perfiles concretos:

| Caso | Probabilidad de muertos | Alerta (>= 0.091) |
|---|---|---|
| Tractocamion Kenworth 2012 en el Cesar, policia de carreteras, diciembre | 0.424 | Si |
| Moto AKT 2023 en Antioquia, policia de carreteras, junio | 0.185 | Si |
| Bus Chevrolet 2010 en Boyaca, policia de carreteras, enero | 0.181 | Si |
| La misma moto AKT 2023, secretaria de Medellin, junio | 0.005 | No |
| Automovil Chevrolet 2015, secretaria de Bogota, marzo | 0.019 | No |

Lectura:

- El tractocamion en carretera es el perfil de mas riesgo: 0.42 es 8 veces la
  prevalencia. Coincide con el EDA (los tractocamiones tienen 28.8% con
  muertos) y con la importancia de tipo y autoridad.
- La misma moto pasa de 0.005 a 0.185 solo por cambiar la autoridad, y en
  carretera queda apenas por encima del bus (0.181). Esto muestra el mayor acierto y el
  mayor riesgo del modelo: acierta en que un siniestro en carretera es mas
  grave, pero parte de esa diferencia es que Medellin casi no registra
  siniestros con muertos.
- Como lo usaria una secretaria o la ANSV: ordenar perfiles por probabilidad
  para elegir donde poner controles (vehiculos de carga y buses en corredores
  viales), y mirar en el tablero los municipios con razon observada/esperada
  muy alejada de 1 como alertas de calidad del registro antes que como
  diagnostico de riesgo.

## Salidas

| Ruta | Contenido |
|---|---|
| `gold/modelos/gradient_boosting.joblib` | `Pipeline` calibrado; `predict_proba` recibe un DataFrame con las 7 variables |
| `gold/modelos/metricas.json` | Particion, busqueda, validacion agrupada, prueba temporal, calibracion, importancia, grupos, casos |
| `gold/modelos/metricas/` | Una fila por modelo y evaluacion |
| `gold/modelos/predicciones/` | Probabilidad por vehiculo (fuera de pliegue 2022-2024, modelo final 2025-2026) |
| `gold/modelos/grupos/` | Grupo de cada municipio con 100 o mas registros |
| `gold/modelos/letalidad/` | Letalidad observada y esperada por municipio |

**Agrupamiento.** 210 municipios con 100 o mas registros (443,675 filas),
variables estandarizadas: proporcion con muertos, edad promedio, proporcion
de motos, de carga y de autoridad nacional, y logaritmo de los registros.
Silueta por k (2 a 8): k-means 0.312, 0.255, 0.241, 0.243, 0.229, 0.221,
0.210; jerarquico de Ward 0.319, 0.236, 0.238, 0.228, 0.223, 0.230, 0.214.
Los dos eligen k = 2 y Ward tiene una silueta apenas mayor, pero se deja
k-means como dice la base del proyecto. El indice de Rand ajustado entre los
dos es 0.28 y las siluetas son bajas: la estructura es debil y los grupos son
mas un gradiente que tipos separados. Grupo 1: 113 municipios urbanos con
415,519 registros, 8.1% con muertos, 62% motos y 19% de autoridad nacional.
Grupo 2: 97 municipios de carretera con 28,156 registros, 24.1% con muertos
en promedio, 17% carga y 70% de registros de la autoridad nacional. En la
tabla de errores por segmento el grupo 2 tiene 96 municipios porque Sesquile
solo tiene registros en 2025-2026. k-means numera los grupos en cada corrida:
en la version `runt-2026-11-20` el 1 era el de carretera y el 2 el urbano.
