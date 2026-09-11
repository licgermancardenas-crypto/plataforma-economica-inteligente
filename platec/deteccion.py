"""
platec.deteccion — detección de maniobras sobre el panel de firmas sintéticas.
==============================================================================
Construye las características observables de cada firma, entrena un clasificador y
lo evalúa con la métrica que corresponde a un problema de detección con clases
desbalanceadas.

QUÉ MIDE Y QUÉ NO
-----------------
Un detector entrenado acá encuentra las maniobras que `firmas_sinteticas` inyectó.
**No dice nada sobre el lavado real.** Sirve para tres cosas y ninguna más: comparar
métodos entre sí sobre un terreno común, medir POTENCIA —cuán chica puede ser una
maniobra y todavía detectarse— y desarrollar el pipeline sin esperar datos
etiquetados que no van a llegar.

POR QUÉ NO SE REPORTA ACCURACY
------------------------------
Con prevalencia del 2%, predecir "todas limpias" acierta el 98%. La exactitud no es
una métrica conservadora acá: es una métrica inservible. Se reportan tres:

- **PR-AUC** (precisión-recall promedio). Es la métrica estándar bajo desbalance
  extremo. El azar vale la prevalencia, no 0,5.
- **ROC-AUC**, que se informa porque es lo que todo el mundo pide, con la advertencia
  de que bajo desbalance extremo **exagera**: se apoya en la tasa de falsos
  positivos, y con 98% de negativos esa tasa se mueve poco aunque las alertas sean
  mayoritariamente falsas.
- **Precisión@k**, que es la única operativamente honesta: un equipo investiga k
  casos por período, y lo que importa es cuántos de esos k eran de verdad.

POR QUÉ LA UNIDAD ES LA FIRMA Y NO EL EJERCICIO
-----------------------------------------------
Se investiga una empresa, no el año fiscal 2022 de una empresa. Además, evaluar por
ejercicio filtraría: los otros ejercicios de la misma firma estarían en el conjunto
de entrenamiento, y varias maniobras son propiedades de la trayectoria. Agregando a
nivel firma, cada fila es independiente y la validación cruzada estándar es válida.

LA FUGA QUE ESTE MÓDULO DESTAPÓ
-------------------------------
La primera corrida dio PR-AUC 0,89 con prevalencia 2%, que para un problema de AML
es demasiado bueno para ser cierto. La causa estaba en el generador, no acá: la
intensidad exportadora de las firmas limpias se sorteaba en [0,00 - 0,35] y la de
las subfacturadoras en [0,45 - 0,85], **soportes disjuntos**. El clasificador
aprendía a reconocer el sorteo, no la maniobra. Lo mismo con la variación entre
ejercicios, que era exactamente cero para toda firma limpia.

Se arregló en `firmas_sinteticas` y el PR-AUC bajó a 0,785. Esa es la razón de ser
de este módulo: **un detector que anda demasiado bien es un diagnóstico sobre el
dataset, no un logro.**
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Columnas que NO pueden entrar nunca a las características: llevan la etiqueta,
# directa o indirectamente. `desvio_maniobra` es cero exactamente en toda firma
# limpia, así que un modelo que la viera resolvería el problema por definición.
COLUMNAS_PROHIBIDAS = frozenset({"tipologia", "maniobra_activa", "desvio_maniobra"})

# Razones observables en un estado contable. Son las que un analista puede calcular
# sin más información que el balance y el estado de resultados de la firma.
_RAZONES = ("margen_rel", "nomina_rel", "ing_sobre_activo_fijo", "apalancamiento",
            "caja_sobre_ingresos", "import_sobre_costos", "export_sobre_ingresos")


def caracteristicas(df: pd.DataFrame, calibraciones: dict) -> pd.DataFrame:
    """
    Matriz de características por FIRMA, a partir de sus estados contables.

    De cada razón se toman la mediana entre ejercicios —el nivel típico de la firma—
    y el desvío —cuánto se mueve—, más dos medidas de trayectoria. El desvío y la
    trayectoria no son adornos: la entidad reactivada es indistinguible en corte
    transversal y sólo aparece ahí.

    Margen y nómina van normalizados por la estructura del sector de la firma: sin
    eso se compara Enseñanza (94% de nómina) contra Minas (29%) y no la maniobra.
    """
    filtradas = COLUMNAS_PROHIBIDAS & set(df.columns)
    d = df.drop(columns=list(filtradas)).sort_values(["firma", "ejercicio"]).copy()

    margen_sector = df["sector"].map(lambda s: calibraciones[s].margen_operativo).values
    nomina_sector = df["sector"].map(lambda s: calibraciones[s].participacion_salarial).values
    d = d.assign(
        margen_rel=(d["resultado_operativo"] / d["ingresos"]) / margen_sector,
        nomina_rel=(d["salarios"] / d["ingresos"]) / nomina_sector,
        ing_sobre_activo_fijo=d["ingresos"] / d["activo_fijo"],
        apalancamiento=d["pasivo"] / d["patrimonio"],
        caja_sobre_ingresos=d["caja"] / d["ingresos"],
        import_sobre_costos=d["importaciones"] / d["otros_costos"],
        export_sobre_ingresos=d["exportaciones"] / d["ingresos"])
    d["crecimiento"] = d.groupby("firma")["ingresos"].pct_change()

    g = d.groupby("firma")
    X = pd.concat([
        g[list(_RAZONES)].median().add_suffix("__nivel"),
        g[list(_RAZONES)].std().add_suffix("__variacion"),
        g["crecimiento"].max().rename("crecimiento__maximo"),
        g["crecimiento"].std().rename("crecimiento__variacion"),
    ], axis=1).replace([np.inf, -np.inf], np.nan)
    return X.fillna(X.median())


def etiquetas(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(y binaria por firma, tipología por firma). Sólo para evaluar, nunca para entrenar."""
    g = df.groupby("firma")["tipologia"].first()
    return g.ne("limpia").astype(int), g


def _modelo(semilla: int):
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(max_iter=300, random_state=semilla)


def evaluar(df: pd.DataFrame, calibraciones: dict, pliegues: int = 5,
            semilla: int = 1, presupuesto: int | None = None) -> dict:
    """
    Validación cruzada del detector sobre el panel. Devuelve métricas y el recall
    por tipología, que es lo que dice QUÉ maniobra se ve y cuál no.

    `presupuesto` es cuántas firmas se alertarían; por defecto, tantas como
    manipuladoras haya (el mejor caso operativo imaginable). Precisión@k con ese
    presupuesto es el número que le importaría a un equipo de investigación.
    """
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    X = caracteristicas(df, calibraciones)
    y, tip = etiquetas(df)
    if y.sum() < pliegues:
        raise ValueError(f"muy pocas firmas con maniobra ({int(y.sum())}) para "
                         f"{pliegues} pliegues: subí n_firmas o la prevalencia")

    p = cross_val_predict(_modelo(semilla), X, y,
                          cv=StratifiedKFold(pliegues, shuffle=True, random_state=semilla),
                          method="predict_proba")[:, 1]

    k = presupuesto if presupuesto is not None else int(y.sum())
    orden = np.argsort(-p)[:k]
    alertadas = pd.Series(False, index=y.index)
    alertadas.iloc[orden] = True

    por_tipologia = {t: float(alertadas.loc[g.index].mean())
                     for t, g in tip[tip.ne("limpia")].groupby(tip)}

    return {
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "precision_en_k": float(y.iloc[orden].mean()),
        "presupuesto": k,
        "azar": float(y.mean()),
        "firmas": int(len(y)),
        "positivas": int(y.sum()),
        "recall_por_tipologia": dict(sorted(por_tipologia.items())),
        "puntajes": pd.Series(p, index=y.index),
    }


def importancia(df: pd.DataFrame, calibraciones: dict, semilla: int = 1,
                repeticiones: int = 5) -> pd.Series:
    """
    Importancia por permutación, medida sobre PR-AUC y no sobre exactitud.

    Sirve menos para interpretar el fenómeno que para AUDITAR EL GENERADOR: si una
    sola característica se lleva todo, lo más probable es que haya una fuga. Así se
    encontró la de los soportes disjuntos.
    """
    from sklearn.inspection import permutation_importance

    X = caracteristicas(df, calibraciones)
    y, _ = etiquetas(df)
    modelo = _modelo(semilla).fit(X, y)
    r = permutation_importance(modelo, X, y, n_repeats=repeticiones,
                               random_state=semilla, scoring="average_precision")
    return pd.Series(r.importances_mean, index=X.columns).sort_values(ascending=False)
