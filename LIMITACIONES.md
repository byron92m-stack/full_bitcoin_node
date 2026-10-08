# Limitaciones de esta auditoría

Documento honesto de lo que **no** cubre la reproducibilidad demostrada en `AUDITORIA.md`. Cada
punto dice qué es, por qué importa y cómo queda acotado.

## 1 · Alcance de la comparación

1. **La referencia es un snapshot móvil.** Se compara contra los 23 CSV de OBM **v0.1.0** tal como
   se publicaron (jul-2026, cubriendo hasta 2026-09-11). OBM puede revisar sus series; esta
   auditoría **no** verifica versiones posteriores, y una revisión suya invalidaría el cruce.
   *Acotado*: el snapshot queda congelado en `obm_reference/`, y `validar_capa3.py` se puede
   re-ejecutar sobre cualquier otro.

2. **"Exacta" = dentro de medio último decimal publicado.** No es una comparación infinitamente
   precisa: en las series publicadas con 8 decimales, una diferencia por debajo de 5e-9 se cuenta
   como coincidencia. Es la única regla razonable, pero conviene saber que el titular "22/23
   bit-exactas" significa eso.

3. **Las series de la referencia no tienen todas la misma longitud** (entre 6.459 y 6.463 fechas).
   El denominador del "22/23" hay que leerlo por serie, no global.

## 2 · Lo que no es bit-exacto

4. **`cdd_btcxdays` no se puede reproducir exactamente, por construcción.** OBM acumula el CDD en
   coma flotante (`A_i` fraccionario) y su propio resultado lleva el redondeo incorporado; nuestro
   cálculo es exacto (dos acumuladores enteros). La diferencia está acotada en **≤1,5 sat-días**
   (≈1,5e-8 BTC-días) y en la práctica afecta a **1 día de 6.461**. *Acotado*: documentado como F2 y
   cuantificado; no es un error de ninguna de las dos partes.

5. **Las ratios que derivan del CDD heredan esa cota** (`dormancy`, `cdd_per_supply`, `liveliness` y
   la tabla ancha de CDD por banda). En este cruce salen exactas, pero **no hay garantía estructural**
   de que lo sigan siendo día a día: cualquier día con residuo por encima de la tolerancia aparecerá
   como diferencia de último dígito.

## 3 · Dependencias y heurísticas del pipeline

6. **La dificultad hay que leerla del nodo (F3).** Por tanto `capa1`–`capa3` **no** son reproducibles
   desde ficheros de bloque aislados: hace falta el RPC. Es una propiedad del método de OBM, no
   nuestra, pero limita la promesa "sólo con el nodo" a *con el nodo en marcha*.

7. **El filtro de "gastabilidad" es una heurística de convención.** El UTXO vivo excluye salidas
   `OP_RETURN`/nulldata y `script_hex` anómalos. Es la convención que hace cuadrar el conteo con
   OBM, pero **no es una propiedad del protocolo**: define la población de outputs de la que hablan
   todas las series de UTXO y coin-age.

8. **El día es UTC según el `time` del bloque**, no `mediantime`. Los timestamps no son monótonos y
   hay **2 inversiones** en 970.447 bloques (F4); se resuelven particionando y escaneando **por
   altura**, de modo que el "día" de un bloque es el de su timestamp, pero el orden de procesado es
   el de la cadena.

## 4 · Convenciones que se replican a propósito

9. **El conteo BIP30 (+2) es una convención, no una verdad.** OBM cuenta las dos copias de los dos
   coinbases duplicados; Core mantiene una. Nuestra `live_outputs` sigue a Core y el ajuste va en
   capa3. Cualquiera que use `capa2/live_outputs.sqlite` directamente obtendrá los conteos **sin**
   ese +2.

10. **Las 12 bandas de edad y los umbrales 155d/365d son las definiciones de OBM**, incluidas sus
    fronteras exactas. Reproducimos *su* partición, no una canónica.

## 5 · Cobertura del dataset

11. **No hay capa4 (precio/mercado).** Quedan fuera todas las series que dependen del precio (NVT,
    MVRV, realized price, hashprice, comisiones en USD). El `ROADMAP.md` la sitúa aparte **a
    propósito**, para no romper la regla de que capa1–capa3 se reproducen sólo con el nodo.

12. **No hay direcciones ni entidades.** Todos los análisis por entidad (rich list, clustering,
    flujos por exchange) están fuera. Son *proxies* sin direcciones (tamaño de output, tipo de
    script, HODL waves, URPD) son más robustos, pero no sustituyen a las entidades.

13. **El dataset termina donde termina la cadena ingerida.** El tip es un objetivo móvil; cualquier
    comparación con OBM (que publica con su propio retardo) es válida sólo en la intersección de
    coberturas.

## 6 · Coste y forma de los datos

14. **Reproducirlo no es barato.** `capa1` son 386 GB de parquet y `capa2` costó **~50-85 min por
    semana** (varios días en total) con unas 8-11 M de inserciones y 7-8 M de borrados por semana.
    Un revisor con menos horas de cómputo no podrá rehacerlo entero.

15. **`capa2` es un SQLite de un solo fichero (~20 GiB), no un sistema distribuido.** Durante una
    semana el WAL llega a ~14 GB. La reproducibilidad es de *proceso*, no de infraestructura.

## 7 · Lo que esta auditoría NO verifica

16. **No audita el código de OBM** (no se usó): verifica la *coincidencia con sus salidas publicadas*,
    no la corrección de su implementación ni de sus decisiones.

17. **No verifica que la referencia sea correcta respecto a la cadena.** Si OBM y nosotros
    compartiéramos una misma interpretación equivocada (por ejemplo, el filtro de gastabilidad o el
    redondeo del CDD), el cruce **no lo detectaría**: coincidiríamos en el error. La auditoría mide
    *acuerdo*, y el acuerdo es evidencia fuerte pero no prueba de verdad.

18. **La prueba bilateral se aplicó a guardas y validadores, no a todas las funciones.** Los cinco
    invariantes y los scripts de reparación se probaron con caso real y caso negativo; el resto del
    código se verifica indirectamente, por la comparación global contra la referencia.

## 8 · Naturaleza de las conclusiones

19. **Nada de esto es inferencia causal ni econometría.** El dataset es una descripción de la
    cadena; las series están autocorrelacionadas y son fuertemente no estacionarias. Cualquier uso
    de estas series para atribuir causas o predecir precios exige, aparte, el tratamiento
    estadístico que el `ROADMAP.md` (Fases 3 y 6) deja explícitamente fuera de esta entrega.
