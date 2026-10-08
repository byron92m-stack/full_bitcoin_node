# Limitaciones de esta auditoría

Documento honesto de lo que **no** cubre la reproducibilidad demostrada en `AUDITORIA.md`. Cada
punto dice qué es, por qué importa y cómo queda acotado.

## 1 · Alcance de la comparación

1. **La referencia es un snapshot móvil.** Se compara contra los 23 CSV de OBM **v0.1.0** tal como
   se publicaron (jul-2026, cubriendo hasta 2026-09-11). OBM puede revisar sus series; esta
   auditoría **no** verifica versiones posteriores, y una revisión suya invalidaría el cruce.
   *Acotado*: el snapshot queda congelado en `obm_reference/`, y `validar_capa3.py` se puede
   re-ejecutar sobre cualquier otro.

2. **"Exacta" = dentro de medio último decimal publicado**, y esa tolerancia se **deriva del propio
   fichero de referencia** (por serie y, en las tablas anchas, por columna), no de una tabla escrita
   a mano: el 2026-10-08 una tabla así decía 8 decimales donde la referencia publica 12, dejaba la
   tolerancia 10.000× más laxa y ocultaba 113 celdas (hallazgo A1 de la revisión adversarial). No es
   una comparación infinitamente precisa: en las series de 8 decimales, una diferencia por debajo de
   5e-9 cuenta como coincidencia. Y en series de magnitud enorme —la dificultad ronda 1,3e14— los 12
   decimales publicados son **ruido de impresión** (el ulp de `float64` es ≈0,016), así que ahí la
   tolerancia es estricta sin ser informativa. El titular "21/23 bit-exactas" significa esta regla.

3. **Las series de la referencia no tienen todas la misma longitud** (entre 6.459 y 6.463 fechas).
   El denominador del "21/23" hay que leerlo por serie, no global.

## 2 · Lo que no es bit-exacto

4. **El CDD no se puede reproducir bit a bit, y no es "coma flotante" genérica.** Con la tolerancia
   publicada quedan dos diferencias: **1 día** en `cdd_btcxdays` (1E-8 = 1 sat-día, el residuo del
   redondeo con que OBM acumula el CDD) y **111 días / 113 celdas** en `cdd_age_band` (1E-12 = 1 ulp
   del último decimal). Esas 113 celdas se comprobaron una a una: son **empates exactos en el
   decimal 13**, nuestra cifra es el redondeo *half-even* del valor exacto en **113/113** y la de OBM
   queda un ulp por debajo. *Acotado*: documentado como F2 con la comprobación incluida; el
   desacuerdo está del lado de OBM.

5. **Las ratios que derivan del CDD heredan esa cota** (`dormancy`, `cdd_per_supply`, `liveliness`).
   En este cruce salen exactas incluso con la tolerancia estricta, pero **no hay garantía
   estructural** de que lo sigan siendo día a día: cualquier día con residuo por encima de la
   tolerancia aparecería como diferencia de último dígito.

## 3 · Dependencias y heurísticas del pipeline

6. **La dificultad hay que leerla del nodo (F3).** Por tanto `capa1`–`capa3` **no** son reproducibles
   desde ficheros de bloque aislados: hace falta el RPC. Es una propiedad del método de OBM, no
   nuestra, pero limita la promesa "sólo con el nodo" a *con el nodo en marcha*.

7. **La tabla de épocas de dificultad hay que refrescarla al extender capa1.** Cubría hasta la
   época 480 y los bloques nuevos caían en la 481: `capa3_series.py` habría usado
   `difficulty_core(bits)` —justo lo que F3 prohíbe— pero **avisa** por pantalla en vez de hacerlo
   en silencio. *Acotado*: se regeneró el 8-oct con el nodo encendido (**482 épocas, 0..481**, tip
   970.449) y el aviso ya no aparece; el riesgo vuelve cada vez que se extienda capa1, y se cierra
   volviendo a lanzar `fix_difficulty_rpc.py`.

8. **El filtro de "gastabilidad" es una heurística de convención.** El UTXO vivo excluye salidas
   `OP_RETURN`/nulldata y `script_hex` anómalos. Es la convención que hace cuadrar el conteo con
   OBM, pero **no es una propiedad del protocolo**: define la población de outputs de la que hablan
   todas las series de UTXO y coin-age.

9. **El día es UTC según el `time` del bloque**, no `mediantime`. Los timestamps no son monótonos y
   hay **2 inversiones que cruzan frontera de semana** en 970.447 bloques (F4); se resuelven
   particionando y escaneando **por altura**, de modo que el "día" de un bloque es el de su
   timestamp, pero el orden de procesado es el de la cadena.

## 4 · Convenciones que se replican a propósito

10. **El conteo BIP30 (+2) es una convención, no una verdad.** OBM cuenta las dos copias de los dos
    coinbases duplicados; Core mantiene una. Nuestra `live_outputs` sigue a Core y el ajuste va en
    capa3. Cualquiera que use `capa2/live_outputs.sqlite` directamente obtendrá los conteos **sin**
    ese +2.

11. **Las 12 bandas de edad y los umbrales 155d/365d son las definiciones de OBM**, incluidas sus
    fronteras exactas. Reproducimos *su* partición, no una canónica.

## 5 · Cobertura del dataset

12. **No hay capa4 (precio/mercado).** Quedan fuera todas las series que dependen del precio (NVT,
    MVRV, realized price, hashprice, comisiones en USD). El `ROADMAP.md` la sitúa aparte **a
    propósito**, para no romper la regla de que capa1–capa3 se reproducen sólo con el nodo.

13. **No hay direcciones ni entidades.** Todos los análisis por entidad (rich list, clustering,
    flujos por exchange) están fuera. Los *proxies* sin direcciones (tamaño de output, tipo de
    script, HODL waves, URPD) son más robustos, pero no sustituyen a las entidades.

14. **El dataset termina donde termina la cadena ingerida.** El tip es un objetivo móvil; cualquier
    comparación con OBM (que publica con su propio retardo) es válida sólo en la intersección de
    coberturas.

## 6 · Coste y forma de los datos

15. **Reproducirlo no es barato.** `capa1` son 388 GiB de parquet y `capa2` costó **~50-85 min por
    semana** (varios días en total) con unas 8-11 M de inserciones y 7-8 M de borrados por semana.
    Un revisor con menos horas de cómputo no podrá rehacerlo entero.

16. **`capa2` es un SQLite de un solo fichero (~20 GiB), no un sistema distribuido.** Durante una
    semana el WAL llega a ~14 GB. La reproducibilidad es de *proceso*, no de infraestructura.

## 7 · Lo que esta auditoría NO verifica

17. **No audita el código de OBM** (no se usó): verifica la *coincidencia con sus salidas
    publicadas*, no la corrección de su implementación ni de sus decisiones.

18. **No verifica que la referencia sea correcta respecto a la cadena.** Si OBM y nosotros
    compartiéramos una misma interpretación equivocada (por ejemplo, el filtro de gastabilidad), el
    cruce **no lo detectaría**: coincidiríamos en el error. La auditoría mide *acuerdo*, y el
    acuerdo es evidencia fuerte pero no prueba de verdad.

19. **La prueba bilateral se aplicó a guardas y validadores, no a todas las funciones.** Los cinco
    invariantes y los scripts de reparación se probaron con caso real y caso negativo; el resto del
    código se verifica indirectamente, por la comparación global contra la referencia.

## 8 · De la documentación

20. **"Cero números a mano" se cumple en el pipeline, no en los documentos.** Los invariantes, la
    validación, las reparaciones y las figuras se regeneran con un script
    (`validar_capa3.py`, `verificar_f7_autocuracion.py`, `graficos_capa3.py`); pero varias cifras de
    los informes son **transcripciones** de ejecuciones anteriores (los estados previos a las
    reparaciones F5 y F7, los recuentos de días de F2, los tamaños) y hoy sólo se reproducen
    rehaciendo el cálculo. Se marcan como históricas cuando aplica.

21. **Las figuras no se auditan mirándolas.** Este modelo no procesa PNG: los pies de figura se
    derivan del código que las dibuja y de las medidas, no de inspección visual. Una figura puede
    estar mal recortada sin que este informe lo detecte.

## 9 · Naturaleza de las conclusiones

22. **Nada de esto es inferencia causal ni econometría.** El dataset es una descripción de la
    cadena; las series están autocorrelacionadas y son fuertemente no estacionarias. Cualquier uso
    de estas series para atribuir causas o predecir precios exige, aparte, el tratamiento
    estadístico que el `ROADMAP.md` (Fases 3 y 6) deja explícitamente fuera de esta entrega.
