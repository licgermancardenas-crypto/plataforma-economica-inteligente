"""
Plataforma Económica Inteligente — Dashboard (Streamlit).
=========================================================
Cockpit de indicadores núcleo + explorador con filtros dinámicos e insights
automáticos + panel de econometría. Se apoya en el núcleo analítico `platec`.

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
                   page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")


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
from platec import insights as ins  # noqa: E402
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
# Estilo (paleta + CSS)
# ---------------------------------------------------------------------------
COLOR = {"primario": "#1f4e79", "acento": "#e67e22", "verde": "#2e8b57",
         "gris": "#7f8c8d", "rojo": "#c0392b", "violeta": "#7d5ba6"}
PALETA = [COLOR["primario"], COLOR["acento"], COLOR["verde"],
          COLOR["violeta"], COLOR["rojo"], COLOR["gris"]]
TONO_COLOR = {"alza": "#c0392b", "baja": "#2e8b57", "alerta": "#e67e22", "neutro": "#7f8c8d"}
TONO_ICONO = {"alza": "🔺", "baja": "🔻", "alerta": "⚠️", "neutro": "•"}

_CSS = """
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1400px;}
  [data-testid="stMetric"] {
      background: #f7f9fb; border: 1px solid #e6ebf0; border-radius: 12px;
      padding: 14px 16px 10px 16px;
  }
  [data-testid="stMetricLabel"] p {font-size: 0.85rem; color: #556; font-weight: 600;}
  [data-testid="stMetricValue"] {font-size: 1.7rem;}
  .insight-card {
      background: #f7f9fb; border-left: 4px solid #1f4e79; border-radius: 8px;
      padding: 10px 14px; margin-bottom: 8px; font-size: 0.92rem; line-height: 1.4;
  }
  .hero {
      background: linear-gradient(100deg, #1f4e79 0%, #2c6ba0 100%);
      color: #fff; padding: 20px 26px; border-radius: 14px; margin-bottom: 18px;
  }
  .hero h1 {color:#fff; font-size: 1.7rem; margin: 0 0 4px 0;}
  .hero p {color:#dce7f2; margin: 0; font-size: 0.95rem;}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Componentes de gráfico
# ---------------------------------------------------------------------------
def _estilo(fig: go.Figure, height: int = 420, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, hovermode="x unified",
        margin=dict(t=54, b=30, l=10, r=10), font=dict(family="sans-serif", size=13),
        title=dict(font=dict(size=16, color=COLOR["primario"])),
        legend=dict(orientation="h", y=-0.18, x=0) if leyenda else dict(),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eef2f5", zeroline=False)
    return fig


def _selector_rango(fig: go.Figure, slider: bool = True) -> go.Figure:
    """Añade botones de rango temporal y (opcional) mini-slider al eje X."""
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1A", step="year", stepmode="backward"),
                dict(count=3, label="3A", step="year", stepmode="backward"),
                dict(count=5, label="5A", step="year", stepmode="backward"),
                dict(step="all", label="Todo"),
            ],
            bgcolor="#eef2f5", activecolor=COLOR["primario"], y=1.12,
        ),
        rangeslider=dict(visible=slider, thickness=0.06),
    )
    return fig


def linea(series: dict[str, pd.Series], titulo: str, ytitulo: str,
          step: bool = False, rango: bool = True, area: bool = False,
          log: bool = False) -> go.Figure:
    fig = go.Figure()
    for i, (nombre, s) in enumerate(series.items()):
        color = PALETA[i % len(PALETA)]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=nombre, mode="lines",
            line=dict(width=2.3, color=color, shape="hv" if step else "linear"),
            fill="tozeroy" if area and len(series) == 1 else None,
            fillcolor="rgba(31,78,121,0.08)" if area else None))
    _estilo(fig, leyenda=len(series) > 1)
    fig.update_layout(title=titulo, yaxis_title=ytitulo)
    if log:
        fig.update_yaxes(type="log")
    if rango:
        _selector_rango(fig)
    return fig


def barras(s: pd.Series, titulo: str, ytitulo: str, rango: bool = False) -> go.Figure:
    colores = [COLOR["rojo"] if v < 0 else COLOR["primario"] for v in s.values]
    fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=colores))
    _estilo(fig, leyenda=False)
    fig.update_layout(title=titulo, yaxis_title=ytitulo)
    if rango:
        _selector_rango(fig, slider=False)
    return fig


def sparkline(s: pd.Series, color: str) -> go.Figure:
    s = s.dropna()
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines",
                               line=dict(width=2, color=color),
                               fill="tozeroy", fillcolor="rgba(31,78,121,0.07)"))
    fig.update_layout(height=70, margin=dict(t=2, b=2, l=2, r=2),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


def panel_insights(items: list[dict], titulo: str = "Lectura automática"):
    st.markdown(f"**🧠 {titulo}**")
    if not items:
        st.caption("Sin observaciones destacadas.")
        return
    for it in items:
        color = TONO_COLOR.get(it["tono"], "#7f8c8d")
        icono = TONO_ICONO.get(it["tono"], "•")
        st.markdown(
            f'<div class="insight-card" style="border-left-color:{color}">'
            f'{icono} {it["texto"]}</div>', unsafe_allow_html=True)


def tabla(s: pd.Series, nombre: str):
    df = s.rename(nombre).reset_index()
    df.columns = ["Fecha", nombre]
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    st.dataframe(df.iloc[::-1], use_container_width=True, height=360, hide_index=True)
    st.download_button("⬇ Descargar CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nombre}.csv", mime="text/csv")


# ---------------------------------------------------------------------------
# Página: Cockpit
# ---------------------------------------------------------------------------
def pagina_cockpit():
    st.markdown(
        '<div class="hero"><h1>📊 Cockpit — Coyuntura económica</h1>'
        '<p>Indicadores núcleo de la macroeconomía argentina · '
        'seguimiento monetario-cambiario</p></div>', unsafe_allow_html=True)

    # sid, label, unidad, freq, malo_si_sube, n_spark
    tiles = [
        ("ipc_general", "Inflación (IPC)", "%", "mensual", True, 24),
        ("usd_oficial", "Dólar oficial", "$", "diario", True, 180),
        ("tamar_priv", "Tasa TAMAR", "% TNA", "diario", False, 180),
        ("emae_desest", "Actividad (EMAE)", "índice", "mensual", False, 36),
        ("reservas", "Reservas", "M US$", "diario", False, 180),
        ("desempleo", "Desempleo", "%", "trimestral", True, 12),
    ]
    cols = st.columns(3)
    for i, (sid, label, unidad, freq, malo, n_spark) in enumerate(tiles):
        r = resumen(sid)
        with cols[i % 3]:
            if sid == "ipc_general":
                valor, delta = f"{r['var_periodo_%']}%", f"{r['var_interanual_%']}% i.a."
            elif sid == "reservas":
                valor, delta = f"{r['ultimo']:,.0f}", f"{r['var_interanual_%']}% i.a."
            elif sid == "desempleo":
                valor, delta = f"{r['ultimo']}%", f"{r['var_interanual_%']} pp i.a."
            else:
                valor, delta = f"{r['ultimo']:,.2f}", f"{r['var_periodo_%']}% vs previo"
            st.metric(label, valor, delta,
                      delta_color="inverse" if malo else "normal")
            st.plotly_chart(sparkline(serie(sid).tail(n_spark), COLOR["primario"]),
                            use_container_width=True, config={"displayModeBar": False})
            st.caption(f"{r['fecha']} · {freq}")

    st.divider()

    # Brecha cambiaria + insights del dólar
    of, ccl = serie("usd_oficial"), serie("usd_ccl")
    br = stats.brecha(ccl, of)
    br.attrs["frequency"] = "D"
    c1, c2 = st.columns([2, 1])
    with c1:
        st.plotly_chart(linea({"Brecha CCL vs oficial %": br}, "Brecha cambiaria", "%",
                              area=True), use_container_width=True)
    with c2:
        st.metric("Brecha actual", f"{br.iloc[-1]:.1f}%",
                  f"{br.iloc[-1] - br.iloc[-22]:.1f} pp vs. ~1 mes",
                  delta_color="inverse")
        panel_insights(ins.insights_serie(br, nombre="la brecha"))


# ---------------------------------------------------------------------------
# Página: Explorador (detalle con filtros dinámicos)
# ---------------------------------------------------------------------------
TRANSFORM = {
    "Nivel": lambda s: s,
    "Variación período previo (%)": lambda s: stats.variacion(s, 1),
    "Variación interanual (%)": lambda s: stats.var_interanual(s),
}


def _aplicar_filtros(s: pd.Series, transform: str, mm: int, log: bool,
                     desde) -> tuple[pd.Series, bool]:
    """Aplica transformación, recorte temporal y media móvil. Devuelve (serie, es_pct)."""
    es_pct = transform != "Nivel"
    out = TRANSFORM[transform](s).dropna()
    if desde is not None:
        out = out[out.index >= pd.Timestamp(desde)]
    if mm > 1:
        out = out.rolling(mm, min_periods=mm).mean().dropna()
    out.attrs.update(s.attrs)
    return out, es_pct


def pagina_explorador():
    st.title("🔎 Explorador de indicadores")
    st.caption("Compará series, cambiá la transformación y filtrá el período. "
               "Los insights se recalculan sobre lo que estás viendo.")
    cat = catalogo()
    nombres = cat.set_index("series_id")["name"].to_dict()

    grupos = {
        "Inflación (IPC)": "inflacion",
        "Tipo de cambio y brecha": "tipo_cambio",
        "Tasa de referencia": "tasa",
        "Actividad (EMAE)": "actividad",
        "Reservas y base monetaria": "monetario",
        "Desempleo (EPH)": "empleo",
    }

    top = st.columns([2, 2])
    grupo = top[0].selectbox("Indicador", list(grupos.keys()))
    series_grupo = cat[cat.indicator_id == grupos[grupo]].series_id.tolist()
    elegidas = top[1].multiselect(
        "Series a comparar", series_grupo,
        default=series_grupo[: min(2, len(series_grupo))],
        format_func=lambda x: nombres.get(x, x))

    f = st.columns([2, 1, 1, 1])
    transform = f[0].radio("Transformación", list(TRANSFORM.keys()), horizontal=True)
    mm = f[1].slider("Media móvil", 1, 12, 1, help="1 = sin suavizado")
    log = f[2].toggle("Escala log", value=False,
                      help="Útil para series con crecimiento exponencial (nivel).")
    anios = f[3].selectbox("Período", ["Todo", "10 años", "5 años", "3 años", "1 año"])

    if not elegidas:
        st.info("Elegí al menos una serie para visualizar.")
        return

    desde = None
    if anios != "Todo":
        n = {"10 años": 10, "5 años": 5, "3 años": 3, "1 año": 1}[anios]
        desde = pd.Timestamp.today() - pd.DateOffset(years=n)

    log_efectivo = log and transform == "Nivel"
    plot_series, es_pct = {}, False
    for sid in elegidas:
        s2, es_pct = _aplicar_filtros(serie(sid), transform, mm, log_efectivo, desde)
        plot_series[nombres.get(sid, sid)] = s2

    ytitulo = "%" if es_pct else "nivel"
    titulo = f"{grupo} — {transform}" + (f" · MM{mm}" if mm > 1 else "")

    graf, tab = st.tabs(["📈 Gráfico", "🗃 Tabla"])
    with graf:
        c1, c2 = st.columns([3, 1])
        with c1:
            usar_barras = es_pct and len(plot_series) == 1
            if usar_barras:
                st.plotly_chart(barras(list(plot_series.values())[0].tail(60),
                                       titulo, ytitulo, rango=True),
                                use_container_width=True)
            else:
                st.plotly_chart(linea(plot_series, titulo, ytitulo, log=log_efectivo),
                                use_container_width=True)
        with c2:
            principal = list(plot_series.values())[0]
            es_tasa = cat.set_index("series_id").loc[elegidas[0], "kind"] == "rate"
            panel_insights(ins.insights_serie(principal, es_tasa=es_tasa,
                                              nombre=nombres.get(elegidas[0], "")))
    with tab:
        sid = st.selectbox("Serie", elegidas, format_func=lambda x: nombres.get(x, x))
        s2, _ = _aplicar_filtros(serie(sid), transform, mm, False, desde)
        tabla(s2, f"{nombres.get(sid, sid)} — {transform}")


# ---------------------------------------------------------------------------
# Página: Econometría
# ---------------------------------------------------------------------------
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
                                   mode="lines+markers",
                                   line=dict(color=COLOR["primario"], width=3),
                                   fill="tozeroy", fillcolor="rgba(31,78,121,0.08)"))
        _estilo(fig, height=340, leyenda=False)
        fig.update_layout(xaxis_title="meses tras la devaluación",
                          yaxis_title="% trasladado a precios")
        st.plotly_chart(fig, use_container_width=True)
        st.metric("Traslado acumulado a 6 meses", f"{pt.acumulado.iloc[-1]*100:.0f}%",
                  help=f"R²={pt.r2}, n={pt.n}")
    with c2:
        st.subheader("Impulso-respuesta (VAR)")
        fig = go.Figure(go.Scatter(x=list(irf.index), y=irf["acumulada"], mode="lines",
                                   line=dict(color=COLOR["acento"], width=3),
                                   fill="tozeroy", fillcolor="rgba(230,126,34,0.08)"))
        _estilo(fig, height=340, leyenda=False)
        fig.update_layout(xaxis_title="meses",
                          yaxis_title="respuesta acum. inflación (pp)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{var}")

    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Curva de Phillips")
        signif = "significativa" if ph.p_valor < 0.05 else "NO significativa"
        st.metric("Pendiente β (desempleo→inflación)", f"{ph.beta_desempleo:+.2f}",
                  f"p={ph.p_valor} ({signif})", delta_color="off")
        st.caption(f"Forma {ph.forma} · R²={ph.r2} · n={ph.n}. En Argentina la relación "
                   "suele ser plana: la inflación la manejan lo monetario/cambiario.")
    with c4:
        st.subheader("Nowcasting de inflación (ML)")
        cc1, cc2 = st.columns(2)
        cc1.metric("Nowcast mes en curso", f"{nc_now:.2f}%",
                   f"últ. oficial {infl_real:.2f}%", delta_color="off")
        cc2.metric("Error vs. benchmark", f"−{nc.mejora_pct:.0f}%",
                   help=f"RMSE {nc.rmse_modelo} vs naive {nc.rmse_naive} ({nc.n_test} meses)")
        st.caption("ElasticNet con variables de alta frecuencia, validación walk-forward. "
                   "Le gana al random walk.")


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Plataforma Económica")
st.sidebar.caption("Monitoreo · Análisis · Econometría")
pagina = st.sidebar.radio("Ir a", ["Cockpit", "Explorador", "Econometría"])
st.sidebar.divider()
st.sidebar.caption("Fuentes: BCRA · INDEC/datos.gob.ar · argentinadatos")

if pagina == "Cockpit":
    pagina_cockpit()
elif pagina == "Explorador":
    pagina_explorador()
else:
    pagina_econometria()
