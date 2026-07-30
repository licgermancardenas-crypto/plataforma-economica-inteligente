"""
Plataforma Económica Inteligente — Dashboard (Streamlit).
=========================================================
Cockpit de indicadores núcleo + vistas de detalle con gráficos y tablas +
panel de econometría. Se apoia en el núcleo analítico `platec`.

Ejecutar local:   streamlit run dashboard/app.py
Deploy:           Streamlit Community Cloud (apunta a este archivo).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar bootstrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bootstrap import ensure_data

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Plataforma Económica Inteligente",
                   page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Carga de datos (cacheada)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Preparando la base de datos (primera vez puede tardar)...")
def _boot():
    ensure_data()
    return True


_boot()
from platec import data, stats  # noqa: E402  (import tras asegurar la DB)
from platec import econometria as ec  # noqa: E402
from platec import nowcast  # noqa: E402


@st.cache_data(ttl=3600)
def serie(sid: str) -> pd.Series:
    return data.get_series(sid)


@st.cache_data(ttl=3600)
def resumen(sid: str) -> dict:
    return stats.resumen(data.get_series(sid))


@st.cache_data(ttl=3600)
def catalogo() -> pd.DataFrame:
    return data.catalogo()


# ---------------------------------------------------------------------------
# Componentes de gráfico
# ---------------------------------------------------------------------------
COLOR = {"primario": "#1f4e79", "acento": "#e67e22", "verde": "#2e8b57",
         "gris": "#7f8c8d", "rojo": "#c0392b"}


def linea(series: dict[str, pd.Series], titulo: str, ytitulo: str,
          step: bool = False) -> go.Figure:
    fig = go.Figure()
    paleta = list(COLOR.values())
    for i, (nombre, s) in enumerate(series.items()):
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=nombre, mode="lines",
            line=dict(width=2, color=paleta[i % len(paleta)],
                      shape="hv" if step else "linear")))
    fig.update_layout(title=titulo, yaxis_title=ytitulo, height=420,
                      hovermode="x unified", margin=dict(t=50, b=20),
                      legend=dict(orientation="h", y=-0.2))
    return fig


def barras(s: pd.Series, titulo: str, ytitulo: str) -> go.Figure:
    fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=COLOR["primario"]))
    fig.update_layout(title=titulo, yaxis_title=ytitulo, height=420,
                      margin=dict(t=50, b=20))
    return fig


def tabla(s: pd.Series, nombre: str):
    df = s.rename(nombre).reset_index()
    df.columns = ["Fecha", nombre]
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    st.dataframe(df.iloc[::-1], use_container_width=True, height=360,
                 hide_index=True)
    st.download_button("⬇ Descargar CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nombre}.csv", mime="text/csv")


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------
def pagina_cockpit():
    st.title("📊 Cockpit — Coyuntura económica")
    st.caption("Indicadores núcleo de la macroeconomía argentina. "
               "Valores más recientes disponibles.")

    tiles = [
        ("Inflación (IPC)", "ipc_general", "%", "mensual"),
        ("Dólar oficial", "usd_oficial", "$", "diario"),
        ("Tasa TAMAR", "tamar_priv", "% TNA", "diario"),
        ("Actividad (EMAE desest.)", "emae_desest", "índice", "mensual"),
        ("Reservas", "reservas", "M US$", "diario"),
        ("Desempleo", "desempleo", "%", "trimestral"),
    ]
    cols = st.columns(3)
    for i, (label, sid, unidad, freq) in enumerate(tiles):
        r = resumen(sid)
        with cols[i % 3]:
            if unidad == "%" and sid in ("ipc_general",):
                valor = f"{r['var_periodo_%']}%"      # inflación = variación
                delta = f"{r['var_interanual_%']}% i.a."
            elif sid == "reservas":
                valor = f"{r['ultimo']:,.0f}"
                delta = f"{r['var_interanual_%']}% i.a."
            elif sid == "desempleo":
                valor = f"{r['ultimo']}%"
                delta = f"{r['var_interanual_%']} pp i.a."
            else:
                valor = f"{r['ultimo']:,.2f}"
                delta = f"{r['var_periodo_%']}% vs previo"
            st.metric(label, valor, delta)
            st.caption(f"{r['fecha']} · {freq}")

    st.divider()
    # Brecha cambiaria destacada
    of, ccl = serie("usd_oficial"), serie("usd_ccl")
    br = stats.brecha(ccl, of)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Brecha CCL vs oficial", f"{br.iloc[-1]:.1f}%",
                  f"{br.iloc[-1] - br.iloc[-22]:.1f} pp vs. ~1 mes")
    with c2:
        st.plotly_chart(linea({"Brecha CCL %": br.tail(365)},
                              "Brecha cambiaria (último año)", "%"),
                        use_container_width=True)


def pagina_detalle():
    st.title("🔎 Detalle por indicador")
    cat = catalogo()
    indicadores = {
        "Inflación (IPC)": "inflacion",
        "Tipo de cambio y brecha": "tipo_cambio",
        "Tasa de referencia": "tasa",
        "Actividad (EMAE)": "actividad",
        "Reservas y base monetaria": "monetario",
        "Desempleo (EPH)": "empleo",
    }
    elegido = st.selectbox("Indicador", list(indicadores.keys()))
    ind = indicadores[elegido]
    series_ind = cat[cat.indicator_id == ind]

    graf, tab = st.tabs(["📈 Gráfico", "🗃 Tabla"])

    with graf:
        if ind == "inflacion":
            infl = stats.var_intermensual(serie("ipc_general")).dropna().tail(36)
            st.plotly_chart(barras(infl, "Inflación mensual (IPC nivel general)", "%"),
                            use_container_width=True)
        elif ind == "tipo_cambio":
            fx = {r["name"]: serie(r.series_id).tail(365)
                  for _, r in series_ind.iterrows() if r.series_id.startswith("usd")}
            st.plotly_chart(linea(fx, "Cotizaciones del dólar (último año)", "ARS/USD"),
                            use_container_width=True)
        elif ind == "tasa":
            st.plotly_chart(linea({"TAMAR (TNA)": serie("tamar_priv")},
                                  "Tasa de referencia TAMAR", "% n.a.", step=True),
                            use_container_width=True)
        elif ind == "actividad":
            st.plotly_chart(linea({"EMAE original": serie("emae_original"),
                                   "EMAE desest.": serie("emae_desest")},
                                  "Actividad económica (EMAE)", "índice 2004=100"),
                            use_container_width=True)
        elif ind == "monetario":
            st.plotly_chart(linea({"Reservas (M US$)": serie("reservas")},
                                  "Reservas internacionales", "millones USD"),
                            use_container_width=True)
            st.plotly_chart(linea({"Base monetaria (M ARS)": serie("base_monetaria")},
                                  "Base monetaria", "millones ARS"),
                            use_container_width=True)
        elif ind == "empleo":
            st.plotly_chart(barras(serie("desempleo").tail(24),
                                   "Tasa de desocupación (EPH)", "%"),
                            use_container_width=True)

    with tab:
        sid = st.selectbox("Serie", series_ind.series_id.tolist(),
                           format_func=lambda x: cat.set_index("series_id").loc[x, "name"])
        tabla(serie(sid), cat.set_index("series_id").loc[sid, "name"])


@st.cache_data(ttl=3600)
def _econometria(anio: str):
    df = data.get_frame(["ipc_general", "usd_oficial"], freq="M", how="last",
                        start=f"{anio}-01-01")
    ipc, tc = df["ipc_general"].dropna(), df["usd_oficial"].dropna()
    pt = ec.pass_through(tc, ipc, lags=6)
    v = pd.DataFrame({"deval": np.log(tc).diff() * 100,
                      "infl": np.log(ipc).diff() * 100}).dropna()
    var = ec.estimar_var(v, maxlags=8)
    irf = ec.irf(var, "deval", "infl", periodos=12)
    infl_q = ipc.resample("QS").last().pct_change() * 100
    ph = ec.curva_phillips(infl_q, data.get_series("desempleo"), aumentada=True)
    d = nowcast.construir_features(start=f"{anio}-01-01")
    nc = nowcast.evaluar_walk_forward(d, min_train=48)
    nc_now = nowcast.nowcast_actual(d)
    return pt, irf, var, ph, nc, nc_now, float(d["infl"].iloc[-1])


def pagina_econometria():
    st.title("🧮 Econometría — relato monetario-cambiario")
    st.caption("Modelado del hilo causal devaluación → precios. "
               "Detalle metodológico en docs/hallazgos_econometricos.md.")
    anio = st.select_slider("Inicio de la muestra", ["2017", "2018", "2019", "2020"],
                            value="2017")
    pt, irf, var, ph, nc, nc_now, infl_real = _econometria(anio)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pass-through cambiario")
        acum = pt.acumulado
        fig = go.Figure(go.Scatter(x=list(acum.index), y=acum.values * 100,
                                   mode="lines+markers", line=dict(color=COLOR["primario"], width=3)))
        fig.update_layout(height=340, xaxis_title="meses tras la devaluación",
                          yaxis_title="% trasladado a precios", margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
        st.metric("Traslado acumulado a 6 meses", f"{pt.acumulado.iloc[-1]*100:.0f}%",
                  help=f"R²={pt.r2}, n={pt.n}")
    with c2:
        st.subheader("Impulso-respuesta (VAR)")
        fig = go.Figure(go.Scatter(x=list(irf.index), y=irf["acumulada"],
                                   mode="lines", line=dict(color=COLOR["acento"], width=3)))
        fig.update_layout(height=340, xaxis_title="meses",
                          yaxis_title="respuesta acum. inflación (pp)", margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{var}")

    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Curva de Phillips")
        signif = "significativa" if ph.p_valor < 0.05 else "NO significativa"
        st.metric("Pendiente β (desempleo→inflación)", f"{ph.beta_desempleo:+.2f}",
                  f"p={ph.p_valor} ({signif})")
        st.caption(f"Forma {ph.forma} · R²={ph.r2} · n={ph.n}. En Argentina la relación "
                   "suele ser plana: la inflación la manejan lo monetario/cambiario.")
    with c4:
        st.subheader("Nowcasting de inflación (ML)")
        cc1, cc2 = st.columns(2)
        cc1.metric("Nowcast mes en curso", f"{nc_now:.2f}%",
                   f"últ. oficial {infl_real:.2f}%")
        cc2.metric("Error vs. benchmark", f"−{nc.mejora_pct:.0f}%",
                   help=f"RMSE {nc.rmse_modelo} vs naive {nc.rmse_naive} ({nc.n_test} meses)")
        st.caption("ElasticNet con variables de alta frecuencia, validación walk-forward. "
                   "Le gana al random walk.")


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Plataforma Económica")
st.sidebar.caption("Monitoreo · Análisis · Econometría")
pagina = st.sidebar.radio("Ir a", ["Cockpit", "Detalle por indicador", "Econometría"])
st.sidebar.divider()
st.sidebar.caption("Fuentes: BCRA · INDEC/datos.gob.ar · argentinadatos")

if pagina == "Cockpit":
    pagina_cockpit()
elif pagina == "Detalle por indicador":
    pagina_detalle()
else:
    pagina_econometria()
