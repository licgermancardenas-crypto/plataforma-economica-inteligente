"""
Plataforma Económica Inteligente — Dashboard (Streamlit).
=========================================================
Cockpit de indicadores núcleo + explorador con filtros dinámicos e insights
automáticos + panel de econometría. Se apoya en el núcleo analítico `platec`.

Estética: SaaS moderno — fondo gris, tarjetas blancas redondeadas, KPI cards con
ícono + pill de variación + sparkline, gauges, sidebar oscuro (solo CSS).

Ejecutar local:   streamlit run dashboard/app.py
Deploy:           Streamlit Community Cloud (apunta a este archivo).
"""
from __future__ import annotations

import inspect
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar bootstrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bootstrap
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
from platec import insights as ins  # noqa: E402
# `econometria` (statsmodels) y `nowcast` (scikit-learn) se importan dentro de la
# página que los usa: son ~2 s de import y el cockpit no los necesita.


@st.cache_data(ttl=3600)
def serie(sid: str) -> pd.Series:
    return data.get_series(sid)


@st.cache_data(ttl=3600)
def resumen(sid: str) -> dict:
    return stats.resumen(data.get_series(sid))


@st.cache_data(ttl=3600)
def catalogo() -> pd.DataFrame:
    return data.catalogo()


def _fecha_datos() -> str:
    """Última observación efectivamente cargada (no la fecha de hoy)."""
    f = bootstrap.estado_datos()["ultima_obs"]
    return pd.Timestamp(f).strftime("%d/%m/%Y") if f else "—"


# ---------------------------------------------------------------------------
# Paleta + estilo
# ---------------------------------------------------------------------------
COLOR = {"primario": "#1f4e79", "acento": "#ef6c57", "teal": "#17a2b8",
         "verde": "#1e9e5a", "gris": "#8895a7", "rojo": "#d64545",
         "violeta": "#7d5ba6", "ambar": "#e0a800"}
PALETA = [COLOR["primario"], COLOR["acento"], COLOR["teal"],
          COLOR["violeta"], COLOR["ambar"], COLOR["verde"]]
TONO_COLOR = {"alza": "#d64545", "baja": "#1e9e5a", "alerta": "#e0a800", "neutro": "#8895a7"}
TONO_ICONO = {"alza": "🔺", "baja": "🔻", "alerta": "⚠️", "neutro": "•"}

# `use_container_width` quedó deprecado en Streamlit 1.49 a favor de `width`, y su
# fecha de remoción ya pasó (31/12/2025): el día que lo saquen, cada gráfico del
# dashboard tira TypeError. El deploy corre siempre la última versión y el entorno
# local puede ir atrás, así que se elige el kwarg que soporte la versión instalada.
ANCHO = ({"width": "stretch"}
         if "width" in inspect.signature(st.plotly_chart).parameters
         else {"use_container_width": True})

_CSS = """
<style>
  /* Fondo gris de la app y tarjetas blancas */
  .stApp {background: #eef1f6;}
  [data-testid="stHeader"] {background: transparent;}
  .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;
      padding-left: 2.2rem; padding-right: 2.2rem;}

  /* Cada st.container(border=True) es una tarjeta */
  [data-testid="stVerticalBlockBorderWrapper"] {
      background: #ffffff; border: 1px solid #e7ecf2 !important;
      border-radius: 16px; padding: 6px 6px;
      box-shadow: 0 1px 3px rgba(20,40,80,.06), 0 6px 20px rgba(20,40,80,.05);
  }
  /* Métricas dentro de tarjeta: sin doble fondo */
  [data-testid="stMetric"] {background: transparent; padding: 6px 10px;}
  [data-testid="stMetricLabel"] p {font-size:.82rem; color:#5a6b80; font-weight:600;}
  [data-testid="stMetricValue"] {font-size:1.6rem; color:#14243f;}

  /* KPI card custom */
  .kpi-head {display:flex; align-items:center; gap:14px; padding:6px 6px 0 6px;}
  .kpi-icon {width:46px; height:46px; border-radius:12px; display:flex;
      align-items:center; justify-content:center; font-size:1.35rem; flex:0 0 auto;}
  .kpi-label {font-size:.82rem; color:#5a6b80; font-weight:600; margin-bottom:1px;}
  .kpi-value {font-size:1.7rem; font-weight:700; color:#14243f; line-height:1.1;}
  .pill {display:inline-block; font-size:.74rem; font-weight:700; padding:2px 8px;
      border-radius:999px; margin-top:3px;}

  /* Insights */
  .insight-card {background:#f7f9fc; border-left:4px solid #1f4e79; border-radius:8px;
      padding:9px 13px; margin-bottom:7px; font-size:.9rem; line-height:1.4; color:#233;}

  /* Hero */
  .hero {background: linear-gradient(100deg,#1f4e79 0%,#2c6ba0 60%,#17a2b8 130%);
      color:#fff; padding:22px 28px; border-radius:16px; margin-bottom:20px;
      box-shadow:0 8px 24px rgba(31,78,121,.25);}
  .hero h1 {color:#fff; font-size:1.65rem; margin:0 0 4px 0;}
  .hero p {color:#dce7f2; margin:0; font-size:.95rem;}

  /* Títulos de sección */
  .section-title {font-size:.78rem; font-weight:700; letter-spacing:.08em;
      text-transform:uppercase; color:#8895a7; margin:8px 0 2px 4px;}

  /* Sidebar oscuro */
  section[data-testid="stSidebar"] {background:#14243f;}
  section[data-testid="stSidebar"] * {color:#e7edf5;}
  section[data-testid="stSidebar"] h1 {color:#fff; font-size:1.15rem;}
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#9fb2cc;}
  section[data-testid="stSidebar"] div[role="radiogroup"] {gap:4px;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label {
      padding:9px 12px; border-radius:10px; margin:1px 0; transition:background .15s;
      cursor:pointer;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:#1e3355;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label p {font-weight:600;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
      background:#ef6c57;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
      color:#fff;}
  section[data-testid="stSidebar"] div[role="radiogroup"] input {display:none;}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def _estilo(fig: go.Figure, height: int = 400, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, hovermode="x unified",
        margin=dict(t=48, b=24, l=8, r=8), font=dict(family="sans-serif", size=13),
        legend=dict(orientation="h", y=-0.18, x=0) if leyenda else dict(),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eef2f6", zeroline=False)
    return fig


def _titulo(fig: go.Figure, texto: str) -> go.Figure:
    fig.update_layout(title=dict(text=texto, font=dict(size=15, color=COLOR["primario"])))
    return fig


def _selector_rango(fig: go.Figure, slider: bool = True) -> go.Figure:
    fig.update_layout(margin=dict(t=76))  # espacio para título + botones
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[dict(count=6, label="6M", step="month", stepmode="backward"),
                     dict(count=1, label="1A", step="year", stepmode="backward"),
                     dict(count=3, label="3A", step="year", stepmode="backward"),
                     dict(count=5, label="5A", step="year", stepmode="backward"),
                     dict(step="all", label="Todo")],
            bgcolor="#eef2f6", activecolor=COLOR["primario"], x=0.5, y=1.16,
            font=dict(size=11)),
        rangeslider=dict(visible=slider, thickness=0.05))
    return fig


def linea(series: dict[str, pd.Series], titulo: str, ytitulo: str,
          step: bool = False, rango: bool = True, area: bool = False,
          log: bool = False) -> go.Figure:
    fig = go.Figure()
    for i, (nombre, s) in enumerate(series.items()):
        color = PALETA[i % len(PALETA)]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=nombre, mode="lines",
            line=dict(width=2.4, color=color, shape="hv" if step else "linear"),
            fill="tozeroy" if area and len(series) == 1 else None,
            fillcolor="rgba(31,78,121,0.08)" if area else None))
    _estilo(fig, leyenda=len(series) > 1)
    _titulo(fig, titulo)
    fig.update_layout(yaxis_title=ytitulo)
    if log:
        fig.update_yaxes(type="log")
    if rango:
        _selector_rango(fig)
    return fig


def barras(s: pd.Series, titulo: str, ytitulo: str, rango: bool = False) -> go.Figure:
    colores = [COLOR["rojo"] if v < 0 else COLOR["primario"] for v in s.values]
    fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=colores))
    _estilo(fig, leyenda=False)
    _titulo(fig, titulo)
    fig.update_layout(yaxis_title=ytitulo)
    if rango:
        _selector_rango(fig, slider=False)
    return fig


def sparkline(s: pd.Series, color: str) -> go.Figure:
    s = s.dropna()
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines",
                               line=dict(width=2, color=color),
                               fill="tozeroy", fillcolor="rgba(31,78,121,0.06)"))
    fig.update_layout(height=56, margin=dict(t=0, b=0, l=0, r=0),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


def gauge(valor: float, titulo: str, rango: list, color: str,
          suffix: str = "%") -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=valor, number=dict(suffix=suffix, font=dict(size=26)),
        title=dict(text=titulo, font=dict(size=13, color="#5a6b80")),
        gauge=dict(axis=dict(range=rango, tickcolor="#8895a7"),
                   bar=dict(color=color, thickness=0.28),
                   bgcolor="#eef2f6", borderwidth=0,
                   steps=[dict(range=[rango[0], rango[1]], color="#f4f7fb")])))
    fig.update_layout(height=210, margin=dict(t=40, b=10, l=20, r=20),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ---------------------------------------------------------------------------
# Componentes UI
# ---------------------------------------------------------------------------
def _pill(delta_num: float, texto: str, malo: bool | None) -> str:
    if malo is None:
        bg, fg = "#eef1f6", "#5a6b80"
    else:
        es_bueno = (delta_num > 0 and not malo) or (delta_num < 0 and malo)
        bg, fg = ("#e7f6ec", "#1e7e46") if es_bueno else ("#fdeaea", "#c0392b")
    flecha = "▲" if delta_num > 0 else ("▼" if delta_num < 0 else "▬")
    return f'<span class="pill" style="background:{bg};color:{fg}">{flecha} {texto}</span>'


def kpi_card(col, icono: str, color: str, label: str, valor: str,
             delta_num: float, delta_txt: str, malo: bool | None,
             spark: pd.Series, sub: str):
    with col:
        with st.container(border=True):
            st.markdown(
                f'<div class="kpi-head">'
                f'<div class="kpi-icon" style="background:{color}1a;color:{color}">{icono}</div>'
                f'<div><div class="kpi-label">{label}</div>'
                f'<div class="kpi-value">{valor}</div>'
                f'{_pill(delta_num, delta_txt, malo)}</div></div>',
                unsafe_allow_html=True)
            st.plotly_chart(sparkline(spark, color), **ANCHO,
                            config={"displayModeBar": False})
            st.caption(sub)


def panel_insights(items: list[dict], titulo: str = "Lectura automática"):
    st.markdown(f"**🧠 {titulo}**")
    if not items:
        st.caption("Sin observaciones destacadas.")
        return
    for it in items:
        color = TONO_COLOR.get(it["tono"], "#8895a7")
        icono = TONO_ICONO.get(it["tono"], "•")
        st.markdown(
            f'<div class="insight-card" style="border-left-color:{color}">'
            f'{icono} {it["texto"]}</div>', unsafe_allow_html=True)


def tabla(s: pd.Series, nombre: str):
    df = s.rename(nombre).reset_index()
    df.columns = ["Fecha", nombre]
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    st.dataframe(df.iloc[::-1], **ANCHO, height=360, hide_index=True)
    st.download_button("⬇ Descargar CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nombre}.csv", mime="text/csv")


def seccion(titulo: str):
    st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Página: Cockpit
# ---------------------------------------------------------------------------
def pagina_cockpit():
    st.markdown(
        f'<div class="hero"><h1>Coyuntura económica argentina</h1>'
        f'<p>Seguimiento monetario-cambiario · última observación: '
        f'{_fecha_datos()}</p></div>',
        unsafe_allow_html=True)

    seccion("Indicadores núcleo")
    # sid, label, icono, color, malo_si_sube, n_spark
    tiles = [
        ("ipc_general", "Inflación (IPC)", "💵", COLOR["acento"], True, 24),
        ("usd_oficial", "Dólar oficial", "💲", COLOR["primario"], True, 180),
        ("tamar_priv", "Tasa TAMAR", "🏦", COLOR["teal"], None, 180),
        ("emae_desest", "Actividad (EMAE)", "🏭", COLOR["verde"], False, 36),
        ("reservas", "Reservas", "💰", COLOR["violeta"], False, 180),
        ("desempleo", "Desempleo", "👷", COLOR["ambar"], True, 12),
    ]
    cols = st.columns(3)
    for i, (sid, label, icono, color, malo, n_spark) in enumerate(tiles):
        r = resumen(sid)
        if sid == "ipc_general":
            valor, dnum, dtxt = f"{r['var_periodo_%']}%", r["var_interanual_%"], f"{r['var_interanual_%']}% i.a."
        elif sid == "reservas":
            valor, dnum, dtxt = f"{r['ultimo']:,.0f}", r["var_interanual_%"], f"{r['var_interanual_%']}% i.a."
        elif sid == "desempleo":
            valor, dnum, dtxt = f"{r['ultimo']}%", r["var_interanual_%"], f"{r['var_interanual_%']} pp i.a."
        else:
            valor, dnum, dtxt = f"{r['ultimo']:,.2f}", r["var_periodo_%"], f"{r['var_periodo_%']}% vs previo"
        kpi_card(cols[i % 3], icono, color, label, valor, dnum, dtxt, malo,
                 serie(sid).tail(n_spark), f"{r['fecha']}")

    st.divider()
    seccion("Tensión cambiaria")
    of, ccl = serie("usd_oficial"), serie("usd_ccl")
    br = stats.brecha(ccl, of)
    br.attrs["frequency"] = "D"
    ipc = serie("ipc_general")

    c1, c2 = st.columns([2, 1])
    with c1:
        with st.container(border=True):
            st.plotly_chart(linea({"Brecha CCL vs oficial %": br}, "Brecha cambiaria", "%",
                                  area=True), **ANCHO)
    with c2:
        with st.container(border=True):
            st.plotly_chart(gauge(float(br.iloc[-1]), "Brecha actual", [0, 120],
                                  COLOR["acento"]), **ANCHO)
        with st.container(border=True):
            infl_m = stats.var_intermensual(ipc).dropna()
            st.plotly_chart(gauge(ins.posicion_historica(infl_m),
                                  "Inflación mensual · percentil histórico",
                                  [0, 100], COLOR["primario"]), **ANCHO)

    seccion("Lectura de la coyuntura")
    ci1, ci2 = st.columns(2)
    with ci1:
        with st.container(border=True):
            panel_insights(ins.insights_serie(br, nombre="la brecha"), "Brecha cambiaria")
    with ci2:
        with st.container(border=True):
            infl_m = stats.var_intermensual(ipc)
            infl_m.attrs["frequency"] = "M"
            panel_insights(ins.insights_serie(infl_m, nombre="la inflación"), "Inflación mensual")


# ---------------------------------------------------------------------------
# Página: Explorador (filtros dinámicos)
# ---------------------------------------------------------------------------
TRANSFORM = {
    "Nivel": lambda s: s,
    "Variación período previo (%)": lambda s: stats.variacion(s, 1),
    "Variación interanual (%)": lambda s: stats.var_interanual(s),
}


def _aplicar_filtros(s: pd.Series, transform: str, mm: int, log: bool,
                     desde) -> tuple[pd.Series, bool]:
    es_pct = transform != "Nivel"
    out = TRANSFORM[transform](s).dropna()
    if desde is not None:
        out = out[out.index >= pd.Timestamp(desde)]
    if mm > 1:
        out = out.rolling(mm, min_periods=mm).mean().dropna()
    out.attrs.update(s.attrs)
    return out, es_pct


def pagina_explorador():
    st.markdown(
        '<div class="hero"><h1>🔎 Explorador de indicadores</h1>'
        '<p>Compará series, cambiá la transformación y filtrá el período · '
        'los insights se recalculan sobre lo que ves</p></div>', unsafe_allow_html=True)
    cat = catalogo()
    nombres = cat.set_index("series_id")["name"].to_dict()
    grupos = {
        "Inflación (IPC)": "inflacion", "Tipo de cambio y brecha": "tipo_cambio",
        "Tasa de referencia": "tasa", "Actividad (EMAE)": "actividad",
        "Reservas y base monetaria": "monetario", "Desempleo (EPH)": "empleo",
    }

    with st.container(border=True):
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
                          help="Solo aplica a 'Nivel'; útil para crecimiento exponencial.")
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
            with st.container(border=True):
                if es_pct and len(plot_series) == 1:
                    st.plotly_chart(barras(list(plot_series.values())[0].tail(60),
                                           titulo, ytitulo, rango=True),
                                    **ANCHO)
                else:
                    st.plotly_chart(linea(plot_series, titulo, ytitulo, log=log_efectivo),
                                    **ANCHO)
        with c2:
            with st.container(border=True):
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
# Cadena del relato: expansión monetaria → presión cambiaria → precios → actividad.
# tc_mayorista y no usd_oficial: el mayorista es el que enfrentan los importadores,
# que es por donde entra el traslado a costos.
CADENA = ["base_monetaria", "tc_mayorista", "ipc_general", "emae_desest"]
ETIQUETA = {"base": "Base monetaria", "tc": "TC mayorista",
            "ipc": "IPC", "emae": "EMAE (desest.)"}


@st.cache_data(ttl=3600, show_spinner="Estimando modelos (VAR, pass-through, nowcast)...")
def _econometria(anio: str):
    from platec import econometria as ec   # statsmodels: import caro, solo acá
    from platec import nowcast             # scikit-learn: idem

    df = data.get_frame(["ipc_general", "usd_oficial"], freq="M", how="last",
                        start=f"{anio}-01-01")
    ipc, tc = df["ipc_general"].dropna(), df["usd_oficial"].dropna()
    pt = ec.pass_through(tc, ipc, lags=6)
    infl_q = ipc.resample("QS").last().pct_change() * 100
    ph = ec.curva_phillips(infl_q, data.get_series("desempleo"), aumentada=True)
    d = nowcast.construir_features(start=f"{anio}-01-01")
    nc = nowcast.evaluar_walk_forward(d, min_train=48)
    nc_now = nowcast.nowcast_actual(d)
    return pt, ph, nc, nc_now, float(d["infl"].iloc[-1])


@st.cache_data(ttl=3600, show_spinner="Estimando el VAR de la cadena y sus bandas (bootstrap)...")
def _cadena(anio: str):
    """VAR de 4 variables + pre-testing + bandas bootstrap + sensibilidad al orden."""
    from platec import econometria as ec

    df = data.get_frame(CADENA, freq="M", how="last", start=f"{anio}-01-01")
    niveles = pd.DataFrame({k: np.log(df[c]) for k, c in
                            zip(ETIQUETA, CADENA)}).dropna()
    v = niveles.diff().mul(100).dropna()          # variaciones % mensuales (log-dif)

    diag_niv = ec.diagnostico(niveles)
    diag_dif = ec.diagnostico(v)
    joh = ec.cointegracion_johansen(niveles)
    var = ec.estimar_var(v, maxlags=6)
    banda = ec.irf_acumulada_bootstrap(v, "tc", "ipc", periodos=12, repl=500)
    ordenes = ec.sensibilidad_orden(v, "tc", "ipc", [
        ["base", "tc", "ipc", "emae"],    # el supuesto del relato
        ["base", "ipc", "tc", "emae"],    # precios antes que el TC
        ["emae", "base", "tc", "ipc"],    # actividad primero
    ])
    granger = pd.DataFrame([
        {"relación": f"{ETIQUETA[a]} → {ETIQUETA[b]}",
         "p mínimo": float(g.p_valor.min()), "en rezago": int(g.p_valor.idxmin())}
        for a, b in [("base", "tc"), ("tc", "ipc"), ("base", "ipc"), ("tc", "emae")]
        for g in [ec.granger(v[a], v[b], maxlag=6, diferenciar=False)]
    ]).set_index("relación")
    return diag_niv, diag_dif, joh, var, banda, ordenes, granger


def pagina_econometria():
    st.markdown(
        '<div class="hero"><h1>🧮 Econometría — relato monetario-cambiario</h1>'
        '<p>Modelado del hilo causal devaluación → precios · '
        'detalle en docs/hallazgos_econometricos.md</p></div>', unsafe_allow_html=True)
    anio = st.select_slider("Inicio de la muestra", ["2017", "2018", "2019", "2020"],
                            value="2017")
    pt, ph, nc, nc_now, infl_real = _econometria(anio)
    diag_niv, diag_dif, joh, var, banda, ordenes, granger = _cadena(anio)

    seccion("Pre-testing: ¿está justificada esta especificación?")
    with st.container(border=True):
        st.caption("Nada de VAR sin verificar antes el orden de integración y la "
                   "cointegración. Esto se corría por consola; ahora se publica junto "
                   "al resultado que justifica.")
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**Niveles (logs)**")
            st.dataframe(diag_niv, **ANCHO)
        with d2:
            st.markdown("**Variaciones mensuales (log-dif)**")
            st.dataframe(diag_dif, **ANCHO)
        rango = joh["rango_cointegracion"]
        if rango == 0:
            st.success(f"**Johansen: rango {rango}** — sin relaciones de cointegración "
                       "entre las cuatro series en niveles, así que el VAR en "
                       "diferencias es la especificación correcta (un VECM sobraría).")
        else:
            st.warning(f"**Johansen: rango {rango}** — hay cointegración: el VAR en "
                       "diferencias está mal especificado y corresponde un VECM. "
                       "Leer las IRF de abajo con esa reserva.")
        ambiguas = diag_dif.index[diag_dif["veredicto"] != "estacionaria (I(0))"].tolist()
        if ambiguas:
            st.warning("Estacionariedad no concluyente en diferencias para: "
                       f"**{', '.join(ETIQUETA.get(a, a) for a in ambiguas)}**. "
                       "En Argentina la inflación mensual es tan persistente que el ADF "
                       "no logra rechazar la raíz unitaria; el VAR sigue siendo la mejor "
                       "opción disponible, pero los errores estándar quedan optimistas.")

    st.divider()
    seccion("Cadena monetaria: shock cambiario → precios")
    c0a, c0b = st.columns([3, 2])
    with c0a:
        with st.container(border=True):
            st.subheader("Respuesta acumulada del IPC, con incertidumbre")
            x = list(banda.puntual.index)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x + x[::-1],
                                     y=list(banda.superior) + list(banda.inferior)[::-1],
                                     fill="toself", fillcolor="rgba(239,108,87,0.16)",
                                     line=dict(width=0), hoverinfo="skip",
                                     name=f"IC {int((1-banda.signif)*100)}%"))
            fig.add_trace(go.Scatter(x=x, y=list(banda.puntual), mode="lines",
                                     line=dict(color=COLOR["acento"], width=3),
                                     name="respuesta acumulada"))
            fig.add_hline(y=0, line=dict(color="#8895a7", width=1, dash="dot"))
            _estilo(fig, height=340, leyenda=True)
            fig.update_layout(xaxis_title="meses tras el shock",
                              yaxis_title="respuesta acum. del IPC (pp)")
            st.plotly_chart(fig, **ANCHO)
            h = banda.puntual.index[-1]
            st.caption(
                f"VAR({banda.p}) sobre {len(banda.orden)} variables, n={banda.n}. "
                f"A {h} meses: **{banda.puntual[h]:.1f} pp** "
                f"[{banda.inferior[h]:.1f}, {banda.superior[h]:.1f}]. "
                f"Bootstrap de residuos, {banda.repl} réplicas — las bandas Monte Carlo "
                "de statsmodels devuelven réplicas idénticas en esta versión y colapsan "
                "sobre el punto, así que el intervalo se calcula acá.")
    with c0b:
        with st.container(border=True):
            st.subheader("Sensibilidad al orden de Cholesky")
            fig = go.Figure()
            for i, col in enumerate(ordenes.columns):
                etiqueta = " → ".join(ETIQUETA.get(t, t) for t in col.split(" → "))
                fig.add_trace(go.Scatter(x=list(ordenes.index), y=ordenes[col],
                                         mode="lines", name=etiqueta,
                                         line=dict(width=2.4, color=PALETA[i % len(PALETA)])))
            fig.add_hline(y=0, line=dict(color="#8895a7", width=1, dash="dot"))
            _estilo(fig, height=340, leyenda=True)
            fig.update_layout(xaxis_title="meses", yaxis_title="respuesta acum. (pp)")
            st.plotly_chart(fig, **ANCHO)
            rango_ord = ordenes.iloc[-1]
            st.caption(
                f"Al horizonte final la respuesta va de **{rango_ord.min():+.1f}** a "
                f"**{rango_ord.max():+.1f} pp** según qué variable se suponga más "
                "exógena. Cholesky impone una cadena contemporánea que los datos no "
                "identifican: si se asume que los precios se mueven antes que el dólar, "
                "el signo se da vuelta. El orden del relato (dinero → dólar → precios → "
                "actividad) es un supuesto económico, no un hallazgo.")

    with st.container(border=True):
        st.markdown("**Causalidad de Granger en la cadena** (p-valor mínimo sobre 6 rezagos)")
        g = granger.copy()
        g["conclusión"] = np.where(g["p mínimo"] < 0.05, "✅ precede", "— no precede")
        g["p mínimo"] = g["p mínimo"].round(4)
        st.dataframe(g, **ANCHO)
        st.caption("Granger es precedencia temporal, no causalidad estructural.")

    st.divider()
    seccion("Traslado a precios")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.subheader("Pass-through cambiario")
            acum = pt.acumulado
            fig = go.Figure(go.Scatter(x=list(acum.index), y=acum.values * 100,
                                       mode="lines+markers",
                                       line=dict(color=COLOR["primario"], width=3),
                                       fill="tozeroy", fillcolor="rgba(31,78,121,0.08)"))
            _estilo(fig, height=320, leyenda=False)
            fig.update_layout(xaxis_title="meses tras la devaluación",
                              yaxis_title="% trasladado a precios")
            st.plotly_chart(fig, **ANCHO)
            st.metric("Traslado acumulado a 6 meses", f"{pt.acumulado.iloc[-1]*100:.0f}%",
                      help=f"R²={pt.r2}, n={pt.n}")
    with c2:
        with st.container(border=True):
            st.subheader("Lectura conjunta")
            st.metric("Traslado a 6 meses (regresión de rezagos distribuidos)",
                      f"{pt.acumulado.iloc[-1]*100:.0f}%", help=f"R²={pt.r2}, n={pt.n}")
            h = banda.puntual.index[-1]
            st.metric(f"Respuesta acumulada del IPC a {h} meses (VAR)",
                      f"{banda.puntual[h]:.1f} pp",
                      f"IC 95%: {banda.inferior[h]:.1f} a {banda.superior[h]:.1f}",
                      delta_color="off")
            st.caption(
                f"{var}. Las dos rutas coinciden en que el traslado existe y es rápido "
                "en los primeros meses, pero el intervalo del VAR es ancho: con ~110 "
                "observaciones mensuales el dato no alcanza para afirmar una magnitud "
                "precisa. La regresión de rezagos distribuidos da un número más "
                "cerrado porque impone que el dólar es exógeno — supuesto que el VAR "
                "no necesita hacer.")

    st.divider()
    seccion("Actividad y proyección")
    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            st.subheader("Curva de Phillips")
            signif = "significativa" if ph.p_valor < 0.05 else "NO significativa"
            st.metric("Pendiente β (desempleo→inflación)", f"{ph.beta_desempleo:+.2f}",
                      f"p={ph.p_valor} ({signif})", delta_color="off")
            st.caption(f"Forma {ph.forma} · R²={ph.r2} · n={ph.n}. En Argentina la relación "
                       "suele ser plana: la inflación la manejan lo monetario/cambiario.")
    with c4:
        with st.container(border=True):
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
st.sidebar.markdown("# 📊 Plataforma Económica")
st.sidebar.caption("Monitoreo · Análisis · Econometría")
st.sidebar.divider()
pagina = st.sidebar.radio("Navegación", ["🏠  Cockpit", "🔎  Explorador", "🧮  Econometría"],
                          label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption(f"📅 Datos hasta {_fecha_datos()}")
if st.sidebar.button("🔄 Actualizar desde las APIs", **ANCHO):
    with st.spinner("Consultando BCRA, INDEC y argentinadatos..."):
        ok, msg = bootstrap.actualizar()
    st.cache_data.clear()
    (st.sidebar.success if ok else st.sidebar.warning)(msg)
st.sidebar.caption("Fuentes: BCRA · INDEC/datos.gob.ar · argentinadatos")

if "Cockpit" in pagina:
    pagina_cockpit()
elif "Explorador" in pagina:
    pagina_explorador()
else:
    pagina_econometria()
