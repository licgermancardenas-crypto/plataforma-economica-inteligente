"""
Plataforma Económica Inteligente — Dashboard (Streamlit).
=========================================================
Cockpit de indicadores núcleo + explorador con filtros dinámicos e insights
automáticos + panel de econometría. Se apoya en el núcleo analítico `platec`.

Estética: SaaS oscuro glassmorphic — fondo navy con glow azul, tarjetas de vidrio
(blur + borde sutil), acento azul eléctrico, KPI cards con ícono + pill de variación
+ sparkline, gauges y sidebar oscuro. Tema base en .streamlit/config.toml.

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


@st.cache_data(ttl=3600)
def indicadores() -> pd.DataFrame:
    return data.indicadores()


def _fecha_datos() -> str:
    """Última observación efectivamente cargada (no la fecha de hoy)."""
    f = bootstrap.estado_datos()["ultima_obs"]
    return pd.Timestamp(f).strftime("%d/%m/%Y") if f else "—"


# ---------------------------------------------------------------------------
# Paleta + estilo
# ---------------------------------------------------------------------------
# Paleta para tema oscuro: tonos brillantes que rinden sobre navy (#0b1220).
# `primario` = azul eléctrico (acento de marca); `acento` = coral cálido de
# contraste. Semántica alza/baja en rojo/verde legibles sobre fondo oscuro.
COLOR = {"primario": "#2b6bff", "acento": "#fb7185", "teal": "#22d3ee",
         "verde": "#34d399", "gris": "#94a3b8", "rojo": "#f87171",
         "violeta": "#a78bfa", "ambar": "#fbbf24"}
PALETA = [COLOR["primario"], COLOR["acento"], COLOR["teal"],
          COLOR["violeta"], COLOR["ambar"], COLOR["verde"]]
TONO_COLOR = {"alza": "#f87171", "baja": "#34d399", "alerta": "#fbbf24", "neutro": "#94a3b8"}
TONO_ICONO = {"alza": "🔺", "baja": "🔻", "alerta": "⚠️", "neutro": "•"}


def _rgba(hex_color: str, alpha: float) -> str:
    """`#rrggbb` → `rgba(r,g,b,alpha)` para rellenos translúcidos bajo cada serie."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"

# `use_container_width` quedó deprecado en Streamlit 1.49 a favor de `width`, y su
# fecha de remoción ya pasó (31/12/2025): el día que lo saquen, cada gráfico del
# dashboard tira TypeError. El deploy corre siempre la última versión y el entorno
# local puede ir atrás, así que se elige el kwarg que soporte la versión instalada.
ANCHO = ({"width": "stretch"}
         if "width" in inspect.signature(st.plotly_chart).parameters
         else {"use_container_width": True})

_CSS = """
<style>
  :root {
      --bg:#0b1220; --surface:rgba(255,255,255,.045); --surface-2:rgba(255,255,255,.07);
      --border:rgba(255,255,255,.09); --border-hi:rgba(43,107,255,.55);
      --fg:#f1f5f9; --fg-muted:#94a3b8; --fg-dim:#64748b; --accent:#2b6bff;
  }
  /* Fondo oscuro con glow radial azul (mood de las referencias) */
  .stApp {
      background:
        radial-gradient(1100px 520px at 12% -8%, rgba(43,107,255,.20), transparent 60%),
        radial-gradient(900px 500px at 100% 0%, rgba(167,139,250,.12), transparent 55%),
        #0b1220;
      background-attachment: fixed;
  }
  [data-testid="stHeader"] {background: transparent;}
  .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;
      padding-left: 2.2rem; padding-right: 2.2rem;}

  /* Cada st.container(border=True) es una tarjeta de vidrio */
  [data-testid="stVerticalBlockBorderWrapper"] {
      background: var(--surface); border: 1px solid var(--border) !important;
      border-radius: 18px; padding: 6px 6px;
      backdrop-filter: blur(14px) saturate(140%);
      -webkit-backdrop-filter: blur(14px) saturate(140%);
      box-shadow: 0 1px 0 rgba(255,255,255,.05) inset, 0 10px 30px rgba(0,0,0,.35);
      transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;
  }
  [data-testid="stVerticalBlockBorderWrapper"]:hover {
      border-color: var(--border-hi) !important;
      box-shadow: 0 1px 0 rgba(255,255,255,.06) inset, 0 14px 40px rgba(0,0,0,.45),
                  0 0 0 1px rgba(43,107,255,.10);
  }
  /* Métricas dentro de tarjeta: sin doble fondo */
  [data-testid="stMetric"] {background: transparent; padding: 6px 10px;}
  [data-testid="stMetricLabel"] p {font-size:.82rem; color:var(--fg-muted); font-weight:600;}
  [data-testid="stMetricValue"] {font-size:1.6rem; color:var(--fg);}

  /* KPI card custom */
  .kpi-head {display:flex; align-items:center; gap:14px; padding:6px 6px 0 6px;}
  .kpi-icon {width:46px; height:46px; border-radius:12px; display:flex;
      align-items:center; justify-content:center; font-size:1.35rem; flex:0 0 auto;
      border:1px solid var(--border);}
  .kpi-label {font-size:.82rem; color:var(--fg-muted); font-weight:600; margin-bottom:1px;}
  .kpi-value {font-size:1.7rem; font-weight:700; color:var(--fg); line-height:1.1;
      letter-spacing:-.01em;}
  .pill {display:inline-block; font-size:.74rem; font-weight:700; padding:2px 8px;
      border-radius:999px; margin-top:3px;}

  /* Insights */
  .insight-card {background:var(--surface); border-left:4px solid var(--accent);
      border:1px solid var(--border); border-radius:10px;
      padding:9px 13px; margin-bottom:7px; font-size:.9rem; line-height:1.4; color:#cbd5e1;}

  /* Hero */
  .hero {background: linear-gradient(105deg,#12203c 0%,#1b2f5e 45%,#3b2a6b 130%);
      border:1px solid var(--border); color:#fff; padding:22px 28px; border-radius:18px;
      margin-bottom:20px; position:relative; overflow:hidden;
      box-shadow:0 12px 40px rgba(0,0,0,.45);}
  .hero::after {content:""; position:absolute; inset:0;
      background: radial-gradient(600px 200px at 90% -40%, rgba(43,107,255,.35), transparent 60%);
      pointer-events:none;}
  .hero h1 {color:#fff; font-size:1.65rem; margin:0 0 4px 0; letter-spacing:-.01em;}
  .hero p {color:#c3cfe6; margin:0; font-size:.95rem;}

  /* Títulos de sección */
  .section-title {font-size:.78rem; font-weight:700; letter-spacing:.10em;
      text-transform:uppercase; color:var(--fg-dim); margin:8px 0 2px 4px;}

  /* Sidebar oscuro glass */
  section[data-testid="stSidebar"] {
      background: linear-gradient(180deg,#0a0f1c 0%,#0b1220 100%);
      border-right:1px solid var(--border);}
  section[data-testid="stSidebar"] h1 {color:#fff; font-size:1.15rem;}
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:var(--fg-muted);}
  section[data-testid="stSidebar"] div[role="radiogroup"] {gap:4px;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label {
      padding:9px 12px; border-radius:10px; margin:1px 0; cursor:pointer;
      border:1px solid transparent; transition:background .15s ease, border-color .15s ease;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
      background:rgba(255,255,255,.05); border-color:var(--border);}
  section[data-testid="stSidebar"] div[role="radiogroup"] label p {font-weight:600; color:#cbd5e1;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
      background:linear-gradient(90deg,rgba(43,107,255,.90),rgba(43,107,255,.65));
      border-color:var(--border-hi);
      box-shadow:0 4px 14px rgba(43,107,255,.35);}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
      color:#fff;}
  section[data-testid="stSidebar"] div[role="radiogroup"] input {display:none;}

  /* Accesibilidad: foco visible para navegación por teclado */
  :focus-visible {outline:2px solid var(--accent) !important; outline-offset:2px;
      border-radius:6px;}
  /* Respetar preferencia de movimiento reducido */
  @media (prefers-reduced-motion: reduce) {
      * {transition:none !important; animation:none !important;}
  }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def _estilo(fig: go.Figure, height: int = 400, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height, hovermode="x unified",
        margin=dict(t=48, b=24, l=8, r=8),
        font=dict(family="sans-serif", size=13, color="#cbd5e1"),
        legend=dict(orientation="h", y=-0.18, x=0) if leyenda else dict(),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="#0e1526", bordercolor="rgba(255,255,255,.12)",
                        font=dict(color="#f1f5f9")))
    fig.update_xaxes(showgrid=False, color="#94a3b8", linecolor="rgba(255,255,255,.10)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False, color="#94a3b8")
    return fig


def _titulo(fig: go.Figure, texto: str) -> go.Figure:
    fig.update_layout(title=dict(text=texto, font=dict(size=15, color="#e8edf6")))
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
            bgcolor="rgba(255,255,255,.06)", activecolor=COLOR["primario"],
            bordercolor="rgba(255,255,255,.12)", font=dict(size=11, color="#cbd5e1"),
            x=0.5, y=1.16),
        rangeslider=dict(visible=slider, thickness=0.05,
                         bgcolor="rgba(255,255,255,.03)"))
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
            fillcolor=_rgba(color, 0.12) if area else None))
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
                               fill="tozeroy", fillcolor=_rgba(color, 0.14)))
    fig.update_layout(height=56, margin=dict(t=0, b=0, l=0, r=0),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


def gauge(valor: float, titulo: str, rango: list, color: str,
          suffix: str = "%") -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=valor,
        number=dict(suffix=suffix, font=dict(size=26, color="#f1f5f9")),
        title=dict(text=titulo, font=dict(size=13, color="#94a3b8")),
        gauge=dict(axis=dict(range=rango, tickcolor="#64748b",
                             tickfont=dict(color="#94a3b8")),
                   bar=dict(color=color, thickness=0.28),
                   bgcolor="rgba(255,255,255,.05)", borderwidth=0,
                   steps=[dict(range=[rango[0], rango[1]], color="rgba(255,255,255,.03)")])))
    fig.update_layout(height=210, margin=dict(t=40, b=10, l=20, r=20),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
    return fig


# ---------------------------------------------------------------------------
# Componentes UI
# ---------------------------------------------------------------------------
def _pill(delta_num: float, texto: str, malo: bool | None) -> str:
    if malo is None:
        bg, fg = "rgba(148,163,184,.16)", "#cbd5e1"
    else:
        es_bueno = (delta_num > 0 and not malo) or (delta_num < 0 and malo)
        bg, fg = (("rgba(52,211,153,.16)", "#6ee7b7") if es_bueno
                  else ("rgba(248,113,113,.16)", "#fca5a5"))
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
    # Los grupos salen de la tabla `indicators`: sumar un indicador al catálogo
    # alcanza para que aparezca acá. Se omiten los que todavía no tienen series.
    con_series = set(cat.indicator_id)
    grupos = {r["name"]: r["indicator_id"] for _, r in indicadores().iterrows()
              if r["indicator_id"] in con_series}

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
# Cadena del relato: riesgo soberano → expansión monetaria → presión cambiaria →
# precios → actividad.
# tc_mayorista y no usd_oficial: el mayorista es el que enfrentan los importadores,
# que es por donde entra el traslado a costos.
# riesgo_pais va PRIMERO en el orden de Cholesky y la justificación es empírica, no
# estética: en el test de Granger ninguna variable del sistema precede al riesgo país
# (todos los p > 0,13), mientras que él sí precede a la actividad (p = 0,003). Es la
# variable más exógena de las cinco en sentido de Granger. Aun así el supuesto pesa:
# ver el panel de sensibilidad al orden.
# ETIQUETA debe seguir el MISMO orden que CADENA: `zip(ETIQUETA, CADENA)` los aparea.
CADENA = ["riesgo_pais", "base_monetaria", "tc_mayorista", "ipc_general", "emae_desest"]
ETIQUETA = {"riesgo": "Riesgo país", "base": "Base monetaria", "tc": "TC mayorista",
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


# VAR diario: el mensual no puede ver si el riesgo país anticipa al dólar en días.
# La brecha entra como log(CCL/mayorista) y no como brecha % — así queda definida aun
# con brecha negativa (2016-19 tuvo mínimos de −17%), y su diferencia es
# Δlog(CCL) − Δlog(mayorista), que no es colineal con Δlog(mayorista).
DIARIO = ["riesgo_pais", "tc_mayorista", "usd_ccl"]
# Se estima POR RÉGIMEN, no pooleado: la brecha promedio va de 0,5% (sin cepo) a 82%
# (cepo II). Son mecanismos distintos y poolearlos mezcla poblaciones.
REGIMENES = {
    "Cepo I (2013-15)":   ("2013-01-01", "2015-12-16"),
    "Sin cepo (2016-19)": ("2015-12-17", "2019-09-01"),
    "Cepo II (2019-23)":  ("2019-09-02", "2023-12-12"),
    "Post-2023":          ("2023-12-13", None),
}
PARES_DIARIOS = [("riesgo", "tc"), ("riesgo", "brecha"), ("brecha", "riesgo"),
                 ("tc", "riesgo"), ("brecha", "tc")]


@st.cache_data(ttl=3600, show_spinner="Estimando el VAR diario por régimen cambiario...")
def _var_diario():
    """
    Granger diario por régimen, con robustez al rezago.

    No se reporta el p-valor "al orden que elige el AIC" porque en esta muestra el
    AIC no converge: elige 3, 15 o 14 según dónde se ponga el tope, mientras BIC
    elige 0 y HQIC 1. Se barre una grilla de rezagos y sólo se llama hallazgo a lo
    que aguanta toda la grilla.
    """
    from platec import econometria as ec

    df = data.get_frame(DIARIO, freq="D").dropna()
    v_all = pd.DataFrame({
        "riesgo": np.log(df["riesgo_pais"]),
        "tc":     np.log(df["tc_mayorista"]),
        "brecha": np.log(df["usd_ccl"] / df["tc_mayorista"]),
    }).diff().mul(100).dropna()

    brecha_pct = (df["usd_ccl"] / df["tc_mayorista"] - 1) * 100
    out = {}
    for nombre, (desde, hasta) in REGIMENES.items():
        v = v_all.loc[desde:hasta]
        b = brecha_pct.loc[desde:hasta]
        out[nombre] = {
            "granger": ec.granger_robusto(v, PARES_DIARIOS),
            "n": len(v), "desde": v.index[0], "hasta": v.index[-1],
            "brecha_media": float(b.mean()), "brecha_sd": float(b.std()),
        }
    return out, len(v_all), v_all.index[0], v_all.index[-1]


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
        ["riesgo", "base", "tc", "ipc", "emae"],   # el supuesto del relato
        ["riesgo", "base", "ipc", "tc", "emae"],   # precios antes que el TC
        ["emae", "riesgo", "base", "tc", "ipc"],   # actividad primero
    ])
    # Canal del riesgo soberano. Se grafica contra la ACTIVIDAD y no contra el TC o el
    # IPC porque es el único destino donde el efecto sobrevive al bootstrap: hacia el
    # TC y el IPC las bandas contienen al cero en los 13 horizontes bajo cualquier
    # ordenamiento. Ver docs/hallazgos_econometricos.md.
    banda_riesgo = ec.irf_acumulada_bootstrap(v, "riesgo", "emae", periodos=12, repl=500)
    ordenes_riesgo = ec.sensibilidad_orden(v, "riesgo", "emae", [
        ["riesgo", "base", "tc", "ipc", "emae"],   # riesgo = condición financiera previa
        ["base", "tc", "ipc", "emae", "riesgo"],   # riesgo = precio de activo, absorbe todo
        ["base", "riesgo", "tc", "ipc", "emae"],
    ])
    granger = pd.DataFrame([
        {"relación": f"{ETIQUETA[a]} → {ETIQUETA[b]}",
         "p mínimo": float(g.p_valor.min()), "en rezago": int(g.p_valor.idxmin())}
        for a, b in [("base", "tc"), ("tc", "ipc"), ("base", "ipc"), ("tc", "emae"),
                     ("riesgo", "tc"), ("riesgo", "ipc"), ("riesgo", "emae"),
                     ("tc", "riesgo")]
        for g in [ec.granger(v[a], v[b], maxlag=6, diferenciar=False)]
    ]).set_index("relación")
    return (diag_niv, diag_dif, joh, var, banda, ordenes, granger,
            banda_riesgo, ordenes_riesgo)


def pagina_econometria():
    st.markdown(
        '<div class="hero"><h1>🧮 Econometría — relato monetario-cambiario</h1>'
        '<p>Modelado del hilo causal devaluación → precios · '
        'detalle en docs/hallazgos_econometricos.md</p></div>', unsafe_allow_html=True)
    anio = st.select_slider("Inicio de la muestra", ["2017", "2018", "2019", "2020"],
                            value="2017")
    pt, ph, nc, nc_now, infl_real = _econometria(anio)
    (diag_niv, diag_dif, joh, var, banda, ordenes, granger,
     banda_riesgo, ordenes_riesgo) = _cadena(anio)

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
                       "entre las cinco series en niveles, así que el VAR en "
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
                                     fill="toself", fillcolor=_rgba(COLOR["acento"], 0.18),
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
            # Trazo distinto por ordenamiento además del color: en escala de grises
            # o con daltonismo, las tres curvas siguen siendo distinguibles (auditoría).
            trazos = ["solid", "dash", "dot"]
            for i, col in enumerate(ordenes.columns):
                etiqueta = " → ".join(ETIQUETA.get(t, t) for t in col.split(" → "))
                fig.add_trace(go.Scatter(x=list(ordenes.index), y=ordenes[col],
                                         mode="lines", name=etiqueta,
                                         line=dict(width=2.4, color=PALETA[i % len(PALETA)],
                                                   dash=trazos[i % len(trazos)])))
            fig.add_hline(y=0, line=dict(color="#8895a7", width=1, dash="dot"))
            _estilo(fig, height=340, leyenda=True)
            fig.update_layout(xaxis_title="meses", yaxis_title="respuesta acum. (pp)")
            st.plotly_chart(fig, **ANCHO)
            rango_ord = ordenes.iloc[-1]
            # El texto se deriva de los números: antes afirmaba un cambio de signo que
            # con la cadena de 5 variables puede no producirse.
            cambia_signo = rango_ord.min() < 0 < rango_ord.max()
            detalle = ("hasta dar vuelta el signo" if cambia_signo
                       else "sin llegar a cambiar de signo")
            st.caption(
                f"Al horizonte final la respuesta va de **{rango_ord.min():+.1f}** a "
                f"**{rango_ord.max():+.1f} pp** según qué variable se suponga más "
                f"exógena, {detalle}. Cholesky impone una cadena contemporánea que los "
                "datos no identifican. El orden del relato (riesgo → dinero → dólar → "
                "precios → actividad) es un supuesto económico, no un hallazgo.")

    with st.container(border=True):
        st.markdown("**Causalidad de Granger en la cadena** (p-valor mínimo sobre 6 rezagos)")
        g = granger.copy()
        g["conclusión"] = np.where(g["p mínimo"] < 0.05, "✅ precede", "— no precede")
        g["p mínimo"] = g["p mínimo"].round(4)
        st.dataframe(g, **ANCHO)
        st.caption("Granger es precedencia temporal, no causalidad estructural.")

    st.divider()
    seccion("Canal del riesgo soberano")
    r1, r2 = st.columns([3, 2])
    with r1:
        with st.container(border=True):
            st.subheader("Respuesta acumulada de la actividad")
            x = list(banda_riesgo.puntual.index)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x + x[::-1],
                                     y=list(banda_riesgo.superior) +
                                       list(banda_riesgo.inferior)[::-1],
                                     fill="toself", fillcolor=_rgba(COLOR["ambar"], 0.16),
                                     line=dict(width=0), hoverinfo="skip",
                                     name=f"IC {int((1-banda_riesgo.signif)*100)}%"))
            fig.add_trace(go.Scatter(x=x, y=list(banda_riesgo.puntual), mode="lines",
                                     line=dict(color=COLOR["ambar"], width=3),
                                     name="respuesta acumulada"))
            fig.add_hline(y=0, line=dict(color="#8895a7", width=1, dash="dot"))
            _estilo(fig, height=340, leyenda=True)
            fig.update_layout(xaxis_title="meses tras el shock",
                              yaxis_title="respuesta acum. del EMAE (pp)")
            st.plotly_chart(fig, **ANCHO)
            h = banda_riesgo.puntual.index[-1]
            n_sig = len(banda_riesgo.significativa_en)
            st.caption(
                f"Shock de 1 d.e. en el riesgo país. A {h} meses la actividad cae "
                f"**{banda_riesgo.puntual[h]:.2f} pp** "
                f"[{banda_riesgo.inferior[h]:.2f}, {banda_riesgo.superior[h]:.2f}], "
                f"significativa en {n_sig} de {h+1} horizontes.")
    with r2:
        with st.container(border=True):
            st.subheader("¿Y hacia el dólar y los precios?")
            st.markdown(
                "**Nada que se pueda sostener.** Hacia el TC mayorista y hacia el IPC "
                "las bandas contienen al cero en los 13 horizontes, con cualquier "
                "ordenamiento de Cholesky. Y el punto estimado hacia el TC se mueve de "
                "**+1,7 pp** a **+0,6 pp** solo con mover el riesgo país del primer al "
                "último lugar del orden: casi todo el efecto aparente era correlación "
                "contemporánea, no dinámica.")
            st.markdown(
                "El canal que sí sobrevive es hacia la **actividad**, y sobrevive bien: "
                "el signo es negativo y significativo bajo los tres ordenamientos, con "
                "el punto entre −0,56 y −0,85 pp. Es el resultado esperable — el riesgo "
                "soberano opera sobre el costo del crédito y la inversión, no sobre el "
                "nivel de precios.")
            st.caption("Contraintuitivo pero robusto: el riesgo país entró al modelo "
                       "como candidato a explicar la dinámica cambiaria y terminó "
                       "explicando la real.")

    with st.container(border=True):
        st.markdown("**Sensibilidad del canal riesgo → actividad al orden de Cholesky**")
        fig = go.Figure()
        trazos = ["solid", "dash", "dot"]
        for i, col in enumerate(ordenes_riesgo.columns):
            etiqueta = " → ".join(ETIQUETA.get(x, x) for x in col.split(" → "))
            fig.add_trace(go.Scatter(x=list(ordenes_riesgo.index), y=ordenes_riesgo[col],
                                     mode="lines", name=etiqueta,
                                     line=dict(width=2.4, color=PALETA[i % len(PALETA)],
                                               dash=trazos[i % len(trazos)])))
        fig.add_hline(y=0, line=dict(color="#8895a7", width=1, dash="dot"))
        _estilo(fig, height=280, leyenda=True)
        fig.update_layout(xaxis_title="meses", yaxis_title="respuesta acum. del EMAE (pp)")
        st.plotly_chart(fig, **ANCHO)
        rr = ordenes_riesgo.iloc[-1]
        st.caption(
            f"Al horizonte final: de **{rr.min():+.2f}** a **{rr.max():+.2f} pp**. "
            "A diferencia del canal cambiario, acá el signo no depende del supuesto de "
            "identificación — que es lo que hace creíble al resultado.")

    st.divider()
    seccion("VAR diario: ¿el riesgo país anticipa al dólar en días?")
    diario, n_tot, d0, d1 = _var_diario()
    with st.container(border=True):
        st.caption(
            f"El VAR mensual colapsa el riesgo país a fin de mes y pierde la dinámica de "
            f"alta frecuencia. Acá se estima en frecuencia diaria sobre "
            f"`[riesgo país, TC mayorista, brecha]` — {n_tot:,} días con las tres series "
            f"({d0:%m/%Y} a {d1:%m/%Y}) — y **por régimen cambiario**, porque la brecha "
            "promedio va de 0,5% sin cepo a 82% bajo el cepo II: poolear mezcla "
            "mecanismos distintos.")
        reg = st.radio("Régimen", list(REGIMENES.keys()), horizontal=True,
                       index=len(REGIMENES) - 1)
        info = diario[reg]
        m = st.columns(3)
        m[0].metric("Días", f"{info['n']:,}")
        m[1].metric("Brecha media", f"{info['brecha_media']:.1f}%")
        m[2].metric("Desvío de la brecha", f"{info['brecha_sd']:.1f} pp")

        g = info["granger"].copy()
        etiq = {"riesgo": "Riesgo país", "tc": "TC mayorista", "brecha": "Brecha"}
        g.index = [" → ".join(etiq.get(x, x) for x in i.split(" → ")) for i in g.index]
        g["robusta"] = np.where(g["robusta"], "✅ robusta", "— frágil")
        st.dataframe(g, **ANCHO)
        st.caption(
            "p-valores de un test de Wald conjunto (todos los rezagos de la causa a la "
            "vez), ajustados por Holm dentro de cada rezago. Se barre la grilla porque "
            "el AIC no converge en diario: elige 3, 15 o 14 según dónde se ponga el "
            "tope, mientras BIC elige 0. **Sólo cuenta como hallazgo lo que aguanta la "
            "grilla entera** — una relación que aparece en un rezago y desaparece en los "
            "vecinos es ruido de selección.")

    with st.container(border=True):
        st.markdown("**Qué contesta esto**")
        st.markdown(
            "La hipótesis que motivó incorporar el riesgo país era que anticipa la "
            "presión cambiaria. **No se sostiene, tampoco en diario.** `Riesgo país → "
            "TC` no es robusta en ningún régimen: en post-2023 aparece significativa a "
            "3 y 15 rezagos y desaparece a 1, 2, 5 y 10 — el patrón típico de un falso "
            "positivo por selección de rezago.")
        st.markdown(
            "Lo que sí aguanta toda la grilla, en post-2023, es la dirección **contraria**: "
            "`brecha → riesgo país` y `brecha → TC`, ambas 6/6. La brecha es el precio "
            "de mercado que se forma libre y lidera; el riesgo soberano la sigue. "
            "Coincide con lo que ya daba el Granger mensual desde que se incorporó la "
            "serie.")
        st.caption("Nota de frecuencia: diferenciar una serie diaria con feriados trata "
                   "un salto de viernes a lunes como un período. Es práctica estándar en "
                   "datos financieros diarios, pero introduce heterocedasticidad — otro "
                   "motivo para leer los p-valores como orden de magnitud.")

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
                                       fill="tozeroy", fillcolor=_rgba(COLOR["primario"], 0.12)))
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
# Página: Gobiernos
# ---------------------------------------------------------------------------
# Qué se puede mirar por mandato. `trans` decide la normalización, que es lo que
# hace comparable un número de 2004 con uno de 2026: 'pct_pib_*' para lo que está
# en pesos, None para lo que ya es un ratio, un índice o dólares.
VISTAS = {
    "Base monetaria (% PBI)":     ("base_monetaria",     "pct_pib_stock", "fin",       "% del PBI"),
    "Reservas BCRA (M USD)":      ("reservas",           None,            "fin",       "millones USD"),
    "Riesgo país (pb)":           ("riesgo_pais",        None,            "promedio",  "puntos básicos"),
    "Resultado primario (% PBI)": ("resultado_primario", "pct_pib_flujo", "promedio",  "% del PBI"),
    "Recaudación (% PBI)":        ("recaudacion_total",  "pct_pib_flujo", "promedio",  "% del PBI"),
    "Saldo comercial (M USD)":    (None,                 "saldo",         "acumulado", "millones USD"),
    "Tipo de cambio mayorista":   ("tc_mayorista",       None,            "var_anual", "ARS/USD"),
    "EMAE (índice 2004=100)":     ("emae_original",      None,            "var_anual", "índice"),
    "Desempleo (%)":              ("desempleo",          None,            "promedio",  "%"),
    "Inflación mensual (%)":      ("inflacion_mensual",  None,            "promedio",  "% mensual"),
}


@st.cache_data(ttl=3600, show_spinner="Calculando comparación entre gobiernos...")
def _gobiernos(vista: str):
    from platec import gobiernos as gob
    sid, trans, como, unidad = VISTAS[vista]
    s = gob._serie_transformada(sid, trans)
    return s, gob.por_gobierno(s, como=como), como, unidad


@st.cache_data(ttl=3600, show_spinner="Armando la tabla comparativa...")
def _tabla_gobiernos():
    from platec import gobiernos as gob
    return gob.tabla_comparativa(), gob.cobertura_matriz()


def _bandas_gobierno(fig: go.Figure, y0: float, y1: float) -> go.Figure:
    """Sombrea el fondo del gráfico por mandato y rotula cada banda."""
    from platec import gobiernos as gob
    for i, p in enumerate(gob.periodos()):
        fig.add_vrect(x0=p.desde, x1=p.hasta, layer="below", line_width=0,
                      fillcolor=PALETA[i % len(PALETA)], opacity=0.10)
        fig.add_annotation(x=p.desde + (p.hasta - p.desde) / 2, y=y1, yanchor="bottom",
                           text=p.nombre, showarrow=False, textangle=-35,
                           font=dict(size=9, color="#94a3b8"))
    return fig


def pagina_gobiernos():
    st.markdown(
        '<div class="hero"><h1>🏛 Comparador de gobiernos</h1>'
        '<p>Cómo varió cada indicador por mandato presidencial · '
        'todo lo que está en pesos va normalizado por PBI</p></div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Por qué no se comparan pesos contra pesos**")
        st.markdown(
            "La base monetaria de 2004 contra la de 2026 en pesos compara inflación, no "
            "política monetaria. Acá todo lo que está en pesos se divide por el **PIB "
            "nominal**: numerador y denominador quedan en pesos del mismo trimestre, así "
            "que no hace falta ningún deflactor — y eso importa, porque el IPC oficial "
            "de 2007-2015 no es creíble y deflactar con él haría que ese tramo se vea "
            "artificialmente bien.")

    vista = st.selectbox("Indicador", list(VISTAS.keys()))
    s, resumen_gob, como, unidad = _gobiernos(vista)

    c1, c2 = st.columns([3, 2])
    with c1:
        with st.container(border=True):
            st.subheader("Evolución, con los mandatos sombreados")
            v = s.dropna()
            fig = go.Figure(go.Scatter(x=v.index, y=v.values, mode="lines",
                                       line=dict(color=COLOR["primario"], width=2),
                                       name=vista))
            _bandas_gobierno(fig, float(v.min()), float(v.max()))
            _estilo(fig, height=400, leyenda=False)
            fig.update_layout(yaxis_title=unidad, xaxis_title=None)
            st.plotly_chart(fig, **ANCHO)
            st.caption(f"{len(v):,} observaciones · {v.index[0]:%m/%Y} a {v.index[-1]:%m/%Y}. "
                       "Los cortes son las fechas de traspaso de mando.")
    with c2:
        with st.container(border=True):
            ETIQ_COMO = {"fin": "valor al final del mandato",
                         "promedio": "promedio del mandato",
                         "acumulado": "acumulado del mandato",
                         "var_anual": "variación anualizada"}
            st.subheader(f"Por gobierno — {ETIQ_COMO.get(como, como)}")
            r = resumen_gob.dropna(subset=["valor"])
            colores = [COLOR["verde"] if x >= 0 else COLOR["acento"] for x in r["valor"]]
            fig = go.Figure(go.Bar(y=r.index, x=r["valor"], orientation="h",
                                   marker_color=colores,
                                   text=[f"{x:,.1f}" for x in r["valor"]],
                                   textposition="auto"))
            fig.add_vline(x=0, line=dict(color="#8895a7", width=1))
            _estilo(fig, height=400, leyenda=False)
            fig.update_layout(xaxis_title=("% anual" if como == "var_anual" else unidad),
                              yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, **ANCHO)
            faltan = resumen_gob["valor"].isna().sum()
            st.caption(
                f"{faltan} de {len(resumen_gob)} mandatos sin dato suficiente para esta "
                "serie (se exige cubrir el 60% del período; si no, se omite en vez de "
                "promediar una punta)." if faltan else
                "Todos los mandatos tienen cobertura suficiente.")

    with st.container(border=True):
        st.markdown("**Detalle del indicador por mandato**")
        d = resumen_gob.copy()
        d["valor"] = d["valor"].round(2)
        d["cobertura"] = (d["cobertura"] * 100).round(0).astype(int).astype(str) + "%"
        d = d.rename(columns={"valor": unidad, "meses": "meses con dato"})
        st.dataframe(d[[unidad, "cobertura", "meses con dato", "desde", "hasta"]], **ANCHO)

    st.divider()
    seccion("Tabla comparativa completa")
    tabla, cob = _tabla_gobiernos()
    with st.container(border=True):
        st.dataframe(
            tabla.style.format("{:,.1f}", na_rep="—")
                 .background_gradient(cmap="RdYlGn", axis=1)
                 .set_properties(**{"font-size": "12px"}),
            **ANCHO)
        st.caption(
            "Color por fila: verde = valor más alto de esa métrica, rojo = más bajo. "
            "**Ojo con la lectura**: alto no es bueno en todas las filas — en riesgo "
            "país o en desempleo el verde es lo malo. El gradiente ordena, no juzga.")

    with st.container(border=True):
        st.markdown("**Cobertura de datos** — qué fracción de cada mandato cubre cada serie")
        st.dataframe(
            cob.style.format("{:.0%}", na_rep="—")
               .background_gradient(cmap="Blues", vmin=0, vmax=1)
               .set_properties(**{"font-size": "12px"}),
            **ANCHO)
        st.caption(
            "Las celdas vacías de la tabla de arriba se explican acá. El riesgo país "
            "arranca en 1999, el PIB —y con él todo lo normalizado— en 2004, y el "
            "resultado primario en 2016: **ninguna comparación desde Menem hasta hoy "
            "es posible para todos los indicadores a la vez**. La inflación tiene un "
            "hueco en CFK I y II porque el IPC de 2007-2015 está marcado INTERVENIDO "
            "y se excluye por defecto.")

    with st.container(border=True):
        st.markdown("**Lo que falta**")
        st.markdown(
            "**Deuda pública.** No está: el Ministerio de Economía la publica en "
            "informes y planillas, no como serie en la API. Lo más cercano disponible "
            "es `intereses_netos` (2016+), que mide la carga del servicio, no el stock. "
            "Incorporarla implica parsear las planillas de la Secretaría de Finanzas.")
        st.caption("Otras ausencias: balanza de pagos, deuda externa privada, "
                   "y el gasto público desagregado antes de 2016.")


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
st.sidebar.markdown("# 📊 Plataforma Económica")
st.sidebar.caption("Monitoreo · Análisis · Econometría")
st.sidebar.divider()
pagina = st.sidebar.radio(
    "Navegación", ["🏠  Cockpit", "🔎  Explorador", "🏛  Gobiernos", "🧮  Econometría"],
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
elif "Gobiernos" in pagina:
    pagina_gobiernos()
else:
    pagina_econometria()
