"""
platec.comercio_espejo — discrepancias espejo del comercio exterior argentino.
==============================================================================
Aparea, para cada año y cada socio, los DOS lados de la misma operación:

    canal exportador   lo que Argentina declara EXPORTAR a P
                       contra lo que P declara IMPORTAR de Argentina
    canal importador   lo que Argentina declara IMPORTAR de P
                       contra lo que P declara EXPORTAR a Argentina

En un mundo sin errores ni maniobras las dos cifras de cada par coinciden. La
diferencia es el insumo de la literatura de flujos financieros ilícitos por mala
facturación comercial: subfacturar exportaciones y sobrefacturar importaciones
son las dos formas clásicas de sacar divisas al tipo de cambio oficial.

TRES ADVERTENCIAS QUE ORGANIZAN TODO EL MÓDULO
----------------------------------------------
1. **La discrepancia cruda NO es mala facturación.** La mayor parte de la brecha
   es lícita: flete y seguro (CIF contra FOB), reexportaciones vía terceros
   países, desfases de timing en el cruce de aduana, clasificación distinta de
   los dos lados y país de origen contra país de procedencia. Este módulo corrige
   solo la primera —la única que los datos permiten corregir con precisión— y
   deja las demás explícitas como advertencia. Lo que devuelve es una
   DISCREPANCIA, no una estimación de flujos ilícitos.

2. **El ajuste CIF/FOB no es un 10% fijo.** Es el supuesto estándar de la
   literatura y en el agregado no está mal (la mediana medida sobre los datos da
   ~9,5%), pero por socio es muy distinto: Brasil ~4%, Estados Unidos ~5%,
   Chile ~11%, Australia ~14%. Es flete, y el flete es distancia. Aplicarle 10%
   a Brasil sobrecorrige seis puntos y puede dar vuelta el signo de la
   discrepancia. Acá el factor se ESTIMA por país declarante a partir de los años
   en que ese país informa las dos valoraciones, y solo se cae a la mediana
   global —también calculada, no supuesta— cuando nunca informa ambas.

3. **Cuando el declarante informa su propio FOB, se usa ese y no se estima
   nada.** Comtrade trae `fobvalue` y `cifvalue` en el mismo registro para una
   parte de los países. Argentina es uno de ellos, incluso en importaciones, así
   que el canal importador no necesita ninguna estimación del lado argentino.

Convención de signos: **gap > 0 significa salida de divisas**. En el canal
exportador, que el socio declare haber recibido más de lo que Argentina declara
haber mandado. En el importador, que Argentina declare haber pagado más de lo que
el socio declara haber mandado.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from .data import DB_PATH

ARGENTINA = 32
MUNDO = 0

# Nombres de los socios principales. Vive en código y no en la base por el mismo
# criterio que el resto del catálogo. Lo que no esté acá se muestra por su código
# M49: no se pierde el dato, solo el nombre.
SOCIOS = {
    76: "Brasil", 156: "China", 842: "Estados Unidos", 152: "Chile",
    276: "Alemania", 724: "España", 380: "Italia", 484: "México",
    604: "Perú", 858: "Uruguay", 68: "Bolivia", 600: "Paraguay",
    392: "Japón", 410: "Corea del Sur", 356: "India", 528: "Países Bajos",
    56: "Bélgica", 124: "Canadá", 250: "Francia", 826: "Reino Unido",
    862: "Venezuela", 764: "Tailandia", 704: "Viet Nam", 360: "Indonesia",
    792: "Turquía", 643: "Rusia", 710: "Sudáfrica", 818: "Egipto",
    36: "Australia", 554: "Nueva Zelanda", 208: "Dinamarca", 616: "Polonia",
    203: "Chequia", 40: "Austria", 756: "Suiza", 752: "Suecia",
    620: "Portugal", 300: "Grecia", 376: "Israel", 682: "Arabia Saudita",
    784: "Emiratos Árabes Unidos", 458: "Malasia", 702: "Singapur",
    170: "Colombia", 218: "Ecuador",
}

# Cotas del factor CIF/FOB admisible. El flete y el seguro de un embarque no son
# el 60% de su valor: un factor fuera de este rango es un error de reporte, no
# un costo de transporte. Medido sobre los datos reales de 2022, el máximo bruto
# sin filtrar llega a 9.993% — un solo registro basura contamina la mediana de un
# país entero si no se acota.
FACTOR_MIN, FACTOR_MAX = 1.0, 1.5


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def nombre_socio(codigo: int) -> str:
    return SOCIOS.get(int(codigo), f"M49 {int(codigo)}")


# ---------------------------------------------------------------------------
# Panel crudo
# ---------------------------------------------------------------------------
def panel(desde: int | None = None, hasta: int | None = None,
          incluir_mundo: bool = False) -> pd.DataFrame:
    """
    El contenido de `trade_mirror`, tal como lo reportó cada país.

    Por defecto excluye el agregado Mundo (partner_code = 0): sumarlo junto a los
    socios bilaterales contaría cada operación dos veces.
    """
    q = ["SELECT year, reporter_code, partner_code, flow_code, "
         "primary_value, fob_value, cif_value FROM trade_mirror WHERE 1=1"]
    params: list = []
    if desde is not None:
        q.append("AND year >= ?"); params.append(int(desde))
    if hasta is not None:
        q.append("AND year <= ?"); params.append(int(hasta))
    if not incluir_mundo:
        q.append("AND partner_code != ?"); params.append(MUNDO)
    with _connect() as con:
        df = pd.read_sql(" ".join(q), con, params=params)
    return df


# ---------------------------------------------------------------------------
# El ajuste CIF/FOB, que es donde se juega la medición
# ---------------------------------------------------------------------------
def factores_cif_fob(df: pd.DataFrame | None = None) -> pd.Series:
    """
    Factor CIF/FOB por país declarante, estimado de sus propios registros.

    Se usan solo las importaciones (`flow_code == 'M'`) en las que el país informó
    las DOS valoraciones: ahí el cociente cif/fob es su margen de flete y seguro
    observado, no un supuesto. Se toma la mediana entre años —robusta a un año
    con un reporte roto— y se acota a [FACTOR_MIN, FACTOR_MAX].

    Devuelve una Series indexada por `reporter_code`. Los países que nunca
    informan ambas valoraciones no aparecen: para ellos se usa `factor_global`.
    """
    d = panel() if df is None else df
    m = d[(d["flow_code"] == "M") & d["cif_value"].notna() & d["fob_value"].notna()]
    m = m[m["fob_value"] > 0]
    if m.empty:
        return pd.Series(dtype="float64", name="factor")
    razon = m["cif_value"] / m["fob_value"]
    ok = m[(razon >= FACTOR_MIN) & (razon <= FACTOR_MAX)].copy()
    ok["razon"] = ok["cif_value"] / ok["fob_value"]
    f = ok.groupby("reporter_code")["razon"].median()
    f.name = "factor"
    return f


def factor_global(df: pd.DataFrame | None = None) -> float:
    """
    Mediana de los factores estimados: el fallback para quien nunca informa FOB.

    Se calcula, no se supone. Que dé cerca del 10% canónico de la literatura es
    una validación del supuesto estándar en el agregado, no una razón para
    imponerlo país por país.
    """
    f = factores_cif_fob(df)
    return float(f.median()) if not f.empty else 1.10


def _valor(v) -> float | None:
    """
    El valor si es un número positivo, None si no.

    NO ES UNA PAVADA DEFENSIVA. Comtrade devuelve `fobvalue = 0` —cero, no null—
    para los países que sencillamente no calculan la valoración FOB. China informa
    su importación desde Argentina de 2020 como cif = 6.814 millones y fob = 0.
    Tomar ese cero como un FOB legítimo hace que el socio "declare" cero contra una
    exportación argentina real, y la discrepancia del año se va a −27.000 millones
    de dólares: el 40% de las exportaciones argentinas, inventado por un cero. En un
    solo año hay 83 registros así, tapando 35 mil millones de dólares de valor.
    Un cero no es un dato faltante en ningún lado salvo acá, y por eso se filtra
    explícitamente en vez de confiar en `notna`.
    """
    if v is None or pd.isna(v) or float(v) <= 0:
        return None
    return float(v)


def _a_fob(fila: pd.Series, factores: pd.Series, global_: float) -> tuple[float, str]:
    """
    Valor FOB de un registro y de dónde salió.

    Jerarquía: el FOB que informó el propio declarante > su CIF deflactado por su
    factor estimado > su CIF deflactado por la mediana global. El origen viaja con
    el número porque no vale lo mismo un FOB reportado que uno imputado.
    """
    fob = _valor(fila["fob_value"])
    if fob is not None:
        return fob, "reportado"
    cif = _valor(fila["cif_value"])
    if cif is None:
        cif = _valor(fila["primary_value"])
    if cif is None:
        return float("nan"), "sin dato"
    f = factores.get(fila["reporter_code"])
    if f is not None and pd.notna(f):
        return float(cif) / float(f), "estimado (factor del país)"
    return float(cif) / global_, "estimado (mediana global)"


# ---------------------------------------------------------------------------
# La discrepancia
# ---------------------------------------------------------------------------
# Cada canal aparea un flujo declarado por Argentina con el flujo espejo del
# socio. Las exportaciones se declaran FOB de los dos lados; las importaciones,
# CIF, y ahí es donde hace falta el ajuste.
#
# EL SIGNO NO ES EL MISMO EN LOS DOS CANALES, y confundirlos suma peras con
# manzanas en el agregado. La maniobra que saca divisas es DECLARAR DE MENOS al
# exportar y DECLARAR DE MÁS al importar:
#
#   exportador   el socio dice haber recibido MÁS de lo que Argentina declara
#                haber mandado          -> salida = socio - argentina
#   importador   Argentina dice haber pagado MÁS de lo que el socio declara
#                haber mandado          -> salida = argentina - socio
#
# Por eso cada canal lleva su orientación y `gap > 0` significa salida de divisas
# en los dos.
_CANALES = {
    # canal: (flujo que declara Argentina, flujo que declara el socio, orientación)
    "exportador": ("X", "M", +1),
    "importador": ("M", "X", -1),
}


def discrepancia(desde: int | None = None, hasta: int | None = None,
                 socios: list[int] | None = None,
                 minimo_usd: float = 50e6,
                 df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Panel año × socio × canal con la discrepancia espejo, todo en FOB.

    `minimo_usd` descarta las relaciones bilaterales chicas: en un par que comercia
    diez millones de dólares al año, un desfase de timing de un solo embarque
    produce una discrepancia porcentual enorme que no dice nada. El umbral se
    aplica al lado argentino.

    Columnas:
      anio, socio_code, socio, canal
      ar_declara      valor FOB que declara Argentina
      socio_declara   valor FOB que declara la contraparte
      gap             socio_declara - ar_declara  (>0 = salida de divisas)
      gap_pct         gap como % de lo que declara Argentina
      origen_ar, origen_socio   'reportado' o 'estimado ...' para cada FOB

    `df` permite inyectar el panel en vez de leerlo de la base: los tests del
    apareo y del ajuste CIF/FOB no necesitan una base ni la red.
    """
    d = panel(desde, hasta) if df is None else df.copy()
    # El agregado Mundo se filtra acá también y no solo en `panel`: con un panel
    # inyectado no pasó por ese filtro, y sumar Mundo junto a los bilaterales
    # contaría cada operación dos veces.
    d = d[d["partner_code"] != MUNDO]
    if d.empty:
        return pd.DataFrame(columns=["anio", "socio_code", "socio", "canal",
                                     "ar_declara", "socio_declara", "gap",
                                     "gap_pct", "origen_ar", "origen_socio"])
    factores = factores_cif_fob(d)
    glob = factor_global(d)

    fob, origen = zip(*(_a_fob(f, factores, glob) for _, f in d.iterrows()))
    d = d.assign(fob=fob, origen=origen)

    ar = d[d["reporter_code"] == ARGENTINA]
    socio = d[d["partner_code"] == ARGENTINA]

    filas = []
    for canal, (flujo_ar, flujo_socio, signo) in _CANALES.items():
        # Los dos lados se indexan por (año, contraparte), pero esa contraparte es
        # `partner_code` en el lado argentino y `reporter_code` en el del socio.
        # Hay que renombrar los niveles o el join no aparea nada.
        clave = ["anio", "socio_code"]
        a = (ar[ar["flow_code"] == flujo_ar]
             .set_index(["year", "partner_code"])[["fob", "origen"]]
             .rename_axis(clave))
        b = (socio[socio["flow_code"] == flujo_socio]
             .set_index(["year", "reporter_code"])[["fob", "origen"]]
             .rename_axis(clave))
        j = a.join(b, how="inner", lsuffix="_ar", rsuffix="_socio")
        for (anio, cod), r in j.iterrows():
            filas.append({"anio": int(anio), "socio_code": int(cod),
                          "socio": nombre_socio(cod), "canal": canal, "_signo": signo,
                          "ar_declara": r["fob_ar"], "socio_declara": r["fob_socio"],
                          "origen_ar": r["origen_ar"], "origen_socio": r["origen_socio"]})

    out = pd.DataFrame(filas)
    if out.empty:
        return out
    if socios:
        out = out[out["socio_code"].isin(socios)]
    out = out[out["ar_declara"] >= minimo_usd].copy()
    out["gap"] = out["_signo"] * (out["socio_declara"] - out["ar_declara"])
    out["gap_pct"] = out["gap"] / out["ar_declara"] * 100
    orden = ["anio", "socio_code", "socio", "canal", "ar_declara", "socio_declara",
             "gap", "gap_pct", "origen_ar", "origen_socio"]
    return out[orden].sort_values(["anio", "canal", "socio"]).reset_index(drop=True)


def por_anio(disc: pd.DataFrame | None = None, **kw) -> pd.DataFrame:
    """
    La discrepancia agregada por año y canal, en millones de dólares.

    `cobertura_fob` es la fracción del valor cuyo FOB salió de un reporte y no de
    una estimación. Es la bandera de calidad de esta medida: con cobertura baja,
    el agregado depende del factor CIF/FOB imputado y hay que decirlo.
    """
    d = discrepancia(**kw) if disc is None else disc
    if d.empty:
        return pd.DataFrame()
    d = d.copy()
    d["_rep"] = (d["origen_socio"] == "reportado") * d["ar_declara"]
    g = d.groupby(["anio", "canal"]).agg(
        ar_declara=("ar_declara", "sum"),
        socio_declara=("socio_declara", "sum"),
        gap=("gap", "sum"),
        socios=("socio_code", "nunique"),
        _rep=("_rep", "sum"))
    g["gap_pct"] = g["gap"] / g["ar_declara"] * 100
    g["cobertura_fob"] = g["_rep"] / g["ar_declara"]
    g = g.drop(columns="_rep")
    for c in ("ar_declara", "socio_declara", "gap"):
        g[c] = g[c] / 1e6            # a millones de USD, como el resto del proyecto
    return g.reset_index()


def serie_anual(canal: str = "exportador", **kw) -> pd.Series:
    """
    La discrepancia de un canal como serie anual (millones USD), indexada por fecha.

    Sale con índice de fechas —1 de enero de cada año— para que se pueda alinear
    contra el resto de la base, que es diaria/mensual/trimestral. Ojo: alinear no
    es tener la misma información. Ver la advertencia de frecuencia en el README.
    """
    g = por_anio(**kw)
    if g.empty:
        return pd.Series(dtype="float64", name=f"discrepancia_{canal}")
    s = g[g["canal"] == canal].set_index("anio")["gap"]
    s.index = pd.to_datetime(s.index.astype(int).astype(str) + "-01-01")
    s.name = f"discrepancia_{canal}"
    return s.sort_index()


def cobertura() -> pd.DataFrame:
    """Qué hay ingerido: años, filas y cuántos países informan las dos valoraciones."""
    d = panel(incluir_mundo=True)
    if d.empty:
        return pd.DataFrame()
    m = d[d["flow_code"] == "M"]
    return pd.DataFrame([{
        "anios": f"{int(d['year'].min())}..{int(d['year'].max())}",
        "filas": len(d),
        "declarantes": d["reporter_code"].nunique(),
        "M con FOB reportado": int(m["fob_value"].notna().sum()),
        "M totales": len(m),
        "factor global estimado": round(factor_global(d), 4),
    }])


# ---------------------------------------------------------------------------
# Contraste contra la brecha cambiaria
# ---------------------------------------------------------------------------
# LA PREGUNTA. Si la discrepancia espejo mide mala facturación motivada por el
# arbitraje cambiario, tiene que crecer con la BRECHA: cuando comprar dólares al
# oficial y venderlos al paralelo deja 80%, subfacturar una exportación o
# sobrefacturar una importación paga ese 80%. Sin brecha no hay premio y la
# maniobra no tiene sentido económico. Es el test que separa una medida contable
# de un hallazgo: si la discrepancia no se mueve con el precio del arbitraje,
# probablemente esté midiendo flete, timing y reexportaciones.
#
# EL PROBLEMA DE POTENCIA, Y POR QUÉ EL PANEL NO ES OPCIONAL. La brecha existe en
# la base desde 2011: quince observaciones anuales. Una regresión de series de
# tiempo con n=15 no distingue casi nada. El panel año × socio × canal da ~1.800
# observaciones y permite absorber con efectos fijos todo lo que es propio de cada
# socio —incluido el error del factor CIF/FOB imputado, que es constante en el
# tiempo para un mismo país—. Pero la brecha es COMÚN a todos los socios de un
# año, así que la información para identificar beta sigue siendo la de quince
# años: el panel mejora la estimación puntual, no multiplica los grados de
# libertad. Por eso se agrupa por año y no por socio.
#
# Y POR QUÉ WILD CLUSTER BOOTSTRAP. Con quince clusters la varianza
# cluster-robusta asintótica está sesgada a la baja y los p-valores salen
# demasiado chicos. Medido acá: el p asintótico del canal exportador da 0,0008 y
# el del bootstrap 0,024 — treinta veces más grande. Reportar el primero sería
# vender como decisivo un resultado que es sugerente. Se implementa el bootstrap
# de Cameron, Gelbach y Miller (2008) con pesos Rademacher e hipótesis nula
# impuesta.

_FUENTES_BRECHA = {"blue": "usd_blue", "ccl": "usd_ccl", "mep": "usd_mep"}


def brecha_anual(fuente: str = "blue") -> pd.Series:
    """
    Brecha cambiaria promedio de cada año, en %, indexada por año (int).

    El blue es la fuente por defecto y no el CCL: arranca en 2011 contra 2013, y
    dos años sobre quince no son un detalle cuando la identificación depende del
    número de años. El CCL queda para robustez.
    """
    from . import data                       # import local: evita ciclo con data

    if fuente not in _FUENTES_BRECHA:
        raise ValueError(f"fuente desconocida: {fuente} (usar {list(_FUENTES_BRECHA)})")
    paralelo = data.get_series(_FUENTES_BRECHA[fuente])
    oficial = data.get_series("usd_oficial")
    b = (paralelo / oficial.reindex(paralelo.index).ffill() - 1) * 100
    s = b.groupby(b.index.year).mean()
    s.name = f"brecha_{fuente}"
    return s


def panel_con_brecha(fuente: str = "blue", desde: int = 2011,
                     solo_reportado: bool = False, **kw) -> pd.DataFrame:
    """
    El panel de discrepancias con la brecha del año pegada y la unidad de panel.

    `solo_reportado` deja únicamente los pares en los que AMBOS lados informaron su
    FOB. Es la robustez que importa: en esa submuestra no interviene ningún factor
    CIF/FOB imputado, así que si el resultado sobrevive ahí no es un artefacto del
    ajuste.
    """
    d = discrepancia(desde=desde, **kw)
    if d.empty:
        return d
    d = d.copy()
    d["brecha"] = d["anio"].map(brecha_anual(fuente))
    d = d.dropna(subset=["brecha", "gap_pct"])
    if solo_reportado:
        d = d[(d["origen_ar"] == "reportado") & (d["origen_socio"] == "reportado")]
    d["unidad"] = d["socio"] + "|" + d["canal"]
    return d


def _beta_t(y, x, unidad_id, anio_id, n_unidades: int) -> tuple[float, float, float]:
    """
    Efectos fijos por unidad + varianza cluster-robusta por año, a mano.

    Los efectos fijos se absorben por transformación within (Frisch-Waugh-Lovell:
    el beta es idéntico al de meter 167 dummies, y es dos órdenes de magnitud más
    rápido, que es lo que hace viable el bootstrap). La corrección de grados de
    libertad descuenta las unidades absorbidas, que es lo que el demeaneo esconde.
    """
    import numpy as np

    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)

    # within: restar la media de cada unidad
    def demean(v):
        s = pd.Series(v).groupby(unidad_id).transform("mean").to_numpy()
        return v - s
    yt, xt = demean(y), demean(x)

    sxx = float(xt @ xt)
    beta = float(xt @ yt) / sxx
    u = yt - beta * xt

    # meat de la sándwich, agrupando por año
    puntajes = pd.Series(xt * u).groupby(anio_id).sum().to_numpy()
    g = len(puntajes)
    n, k = len(y), n_unidades + 1
    correccion = (g / (g - 1)) * ((n - 1) / (n - k))
    var = correccion * float(puntajes @ puntajes) / sxx ** 2
    se = float(var) ** 0.5
    return beta, se, beta / se


def contraste_brecha(canal: str = "exportador", fuente: str = "blue",
                     desde: int = 2011, solo_reportado: bool = False,
                     excluir_anios: tuple[int, ...] = (), repl: int = 999,
                     seed: int = 7, df: pd.DataFrame | None = None) -> dict:
    """
    ¿La discrepancia del canal crece con la brecha cambiaria?

    Estima `gap_pct[socio,t] = a_socio + beta * brecha[t] + e` con efectos fijos por
    socio y error agrupado por año, y calibra el p-valor con wild cluster bootstrap.

    `beta` se lee como: puntos porcentuales de discrepancia (sobre el comercio del
    par) por cada punto porcentual de brecha.
    """
    import numpy as np

    d = panel_con_brecha(fuente, desde, solo_reportado) if df is None else df.copy()
    if not d.empty:
        d = d[d["canal"] == canal]
        if excluir_anios:
            d = d[~d["anio"].isin(excluir_anios)]
    if len(d) < 30 or d["anio"].nunique() < 5:
        raise ValueError(f"muestra insuficiente para el contraste: n={len(d)}, "
                         f"años={d['anio'].nunique() if len(d) else 0}")

    unidad = d["unidad"].to_numpy()
    anio = d["anio"].to_numpy()
    n_u = d["unidad"].nunique()
    y = d["gap_pct"].to_numpy(dtype=float)
    x = d["brecha"].to_numpy(dtype=float)

    beta, se, t_obs = _beta_t(y, x, unidad, anio, n_u)

    # Bootstrap con la nula impuesta: el modelo restringido es solo los efectos
    # fijos, y se remuestrean sus residuos con un signo por AÑO (no por
    # observación), que es lo que respeta la correlación dentro del cluster.
    residuo = y - pd.Series(y).groupby(unidad).transform("mean").to_numpy()
    ajustado = y - residuo
    rng = np.random.default_rng(seed)
    anios = np.unique(anio)
    idx = {a: i for i, a in enumerate(anios)}
    pos = np.array([idx[a] for a in anio])

    extremos = 0
    for _ in range(repl):
        w = rng.choice([-1.0, 1.0], size=len(anios))
        y_b = ajustado + residuo * w[pos]
        _, _, t_b = _beta_t(y_b, x, unidad, anio, n_u)
        if abs(t_b) >= abs(t_obs):
            extremos += 1

    return {"canal": canal, "fuente": fuente, "beta": beta, "se": se, "t": t_obs,
            "p_wcb": (extremos + 1) / (repl + 1), "n": len(d),
            "unidades": n_u, "anios": int(d["anio"].nunique()), "repl": repl,
            "solo_reportado": solo_reportado}
