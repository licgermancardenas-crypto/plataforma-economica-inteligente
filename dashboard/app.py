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
import os
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
from platec import narrador as nar  # noqa: E402
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

  /* Lectura redactada (capa de IA) */
  .narrador-card {background:linear-gradient(180deg, rgba(43,107,255,.10), rgba(43,107,255,.03));
      border:1px solid rgba(43,107,255,.28); border-radius:12px;
      padding:14px 16px; font-size:.93rem; line-height:1.55; color:#dbe4f3;}
  .narrador-card.sin-verificar {background:linear-gradient(180deg, rgba(251,191,36,.10), rgba(251,191,36,.03));
      border-color:rgba(251,191,36,.40);}
  .narrador-meta {font-size:.72rem; color:var(--fg-muted); margin-top:8px;
      letter-spacing:.04em; text-transform:uppercase;}

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


# ---------------------------------------------------------------------------
# Capa de IA: lectura redactada, verificada contra los números de la plataforma
# ---------------------------------------------------------------------------
def _credenciales_llm() -> bool:
    """
    Pasa la credencial de `st.secrets` al entorno, que es donde la busca platec.narrador.
    El módulo no conoce Streamlit a propósito: se usa igual desde un script o un notebook.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        clave = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        clave = None                      # sin secrets.toml, st.secrets levanta excepción
    if clave:
        os.environ["ANTHROPIC_API_KEY"] = str(clave)
        return True
    return False


def _render_lectura(lec, dossier, clave: str):
    css = "narrador-card" + ("" if lec.verificado else " sin-verificar")
    st.markdown(f'<div class="{css}">{lec.texto}</div>', unsafe_allow_html=True)

    if lec.verificado:
        estado = "✓ todos los números verificados contra el dossier"
    else:
        estado = ("⚠ sin verificar — estos números no están en el dossier: "
                  + ", ".join(lec.numeros_huerfanos))
    origen = "del caché" if lec.desde_cache else f"generada ahora · {lec.intentos} intento(s)"
    st.markdown(f'<div class="narrador-meta">{estado} · {origen}</div>',
                unsafe_allow_html=True)

    if not lec.verificado:
        st.warning(
            "El modelo escribió al menos un número que la plataforma no calculó. El texto "
            "se muestra igual, marcado: ocultarlo sería peor que exhibirlo. No uses esos "
            "valores sin comprobarlos en el dossier.")

    with st.expander("Ver el dossier que recibió el modelo"):
        st.caption("Esto es TODO lo que el modelo tuvo a la vista. No calcula: redacta.")
        st.code(dossier.a_texto(), language="markdown")
        if st.button("🔄 Rehacer la lectura", key=f"rehacer_{clave}"):
            with st.spinner("Redactando..."):
                try:
                    nar.redactar(dossier, forzar=True)
                except RuntimeError as e:
                    st.warning(f"No se pudo rehacer: {e}")
                    return
            st.rerun()


def panel_narrador(construir_dossier, clave: str, titulo: str = "Lectura del analista"):
    """
    Panel de la capa de IA. Dos decisiones deliberadas:

    - **No llama al modelo en cada rerun.** Streamlit reejecuta el script ante cualquier
      interacción; llamar ahí sería pagar una redacción por cada click. Si ya hay una
      lectura cacheada para ESTOS datos se muestra sola; si no, hay que pedirla.
    - **Sin credenciales no aparece un botón muerto**, sino la explicación de qué falta.
      El panel determinístico de al lado sigue funcionando igual: la IA es un agregado.
    """
    st.markdown(f"**✍️ {titulo}**")
    try:
        dossier = construir_dossier()
    except (KeyError, ValueError) as e:
        st.caption(f"Sin dossier para esta selección: {e}")
        return

    lec = nar.cacheada(dossier)
    if lec is None:
        if not _credenciales_llm():
            st.caption(
                "Capa de IA sin configurar. Definí `ANTHROPIC_API_KEY` como secret del "
                "deploy o como variable de entorno. El panel de lectura automática no la "
                "necesita: sigue funcionando sin API.")
            return
        st.caption(
            "El modelo redacta sobre los hechos que ya calculó la plataforma — no calcula "
            "nada por su cuenta — y cada número del texto se verifica contra el dossier "
            "antes de mostrarse.")
        if not st.button("✍️ Redactar lectura", key=f"nar_{clave}", **ANCHO):
            return
        with st.spinner("Redactando..."):
            try:
                lec = nar.redactar(dossier)
            except RuntimeError as e:
                st.warning(f"No se pudo redactar: {e}")
                return
    _render_lectura(lec, dossier, clave)


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
            with st.container(border=True):
                # Sobre la serie CRUDA, no sobre `principal`: los filtros de la UI
                # (transformación, media móvil, recorte) cambian lo que se grafica, y
                # redactar sobre eso obligaría a explicarle al modelo cada filtro.
                panel_narrador(lambda: nar.dossier_serie(elegidas[0]),
                               clave=f"serie_{elegidas[0]}")
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


@st.cache_data(ttl=3600, show_spinner="Testeando estabilidad de parámetros (bootstrap)...")
def _estabilidad(anio: str):
    """Sup-Wald por ecuación + la función de potencia de la ecuación del IPC."""
    from platec import econometria as ec

    df = data.get_frame(CADENA, freq="M", how="last", start=f"{anio}-01-01")
    niveles = pd.DataFrame({k: np.log(df[c]) for k, c in zip(ETIQUETA, CADENA)}).dropna()
    v = niveles.diff().mul(100).dropna()
    tests = [ec.estabilidad(v, eq, repl=499) for eq in ETIQUETA]
    # La potencia se mide sobre la ecuación del IPC porque es la que sostiene el
    # pass-through, que es el resultado que se publica arriba.
    general = ec.potencia_estabilidad(v, "ipc", "pendientes", (0.5, 1.0, 2.0),
                                      repl_nula=299, repl=200)
    puntual = ec.potencia_estabilidad(v, "ipc", "un_coeficiente", (6.0, 15.0, 30.0),
                                      coeficiente="tc_l1", repl_nula=299, repl=200)
    return tests, general, puntual


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
    # Los retornos del riesgo país se calculan ANULANDO los días de recomposición del
    # EMBI+ (ver stats.RECOMPOSICIONES_EMBI). El 10/09/2020, con la liquidación del
    # canje, el índice cae de 2.120 a 1.101 puntos: es un cambio de qué mide, no un
    # movimiento de mercado, y en esta muestra ese único día aportaba el 13% de la
    # suma de cuadrados de la serie. Sin anularlo, la relación TC → riesgo país en
    # Cepo II se leía como no robusta (4/6) cuando es robusta (6/6).
    v_all = pd.DataFrame({
        "riesgo": stats.log_dif(df["riesgo_pais"], stats.RECOMPOSICIONES_EMBI),
        "tc":     stats.log_dif(df["tc_mayorista"]),
        "brecha": stats.log_dif(df["usd_ccl"] / df["tc_mayorista"]),
    }).dropna()

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


# Sistema BIVARIADO [riesgo país, TC], sin brecha. Sacando la brecha se pierde una
# variable y se ganan once años: el CCL arranca en 2013 y el TC mayorista en 2002-03.
# No arranca en 1999 —aunque el riesgo país sí— porque durante la convertibilidad el
# peso estaba fijo por ley: no hay tipo de cambio que modelar, y el BCRA empieza a
# publicar la serie cuando empieza la flotación.
LARGO = ["riesgo_pais", "tc_mayorista"]
REGIMENES_LARGO = {
    "Default (2002-05)":       ("2002-03-04", "2005-06-10"),
    "Normalización (2005-11)": ("2005-06-14", "2011-10-30"),
    "Cepo I (2011-15)":        ("2011-10-31", "2015-12-16"),
    "Sin cepo (2016-19)":      ("2015-12-17", "2019-09-01"),
    "Cepo II (2019-23)":       ("2019-09-02", "2023-12-12"),
    "Post-2023":               ("2023-12-13", None),
}
PARES_LARGO = [("riesgo", "tc"), ("tc", "riesgo")]


@st.cache_data(ttl=3600, show_spinner="Estimando el VAR diario largo (2002-hoy)...")
def _var_largo():
    """Granger por régimen sobre el sistema bivariado, con once años más de muestra."""
    from platec import econometria as ec

    df = data.get_frame(LARGO, freq="D").dropna()
    v = pd.DataFrame({
        "riesgo": stats.log_dif(df["riesgo_pais"], stats.RECOMPOSICIONES_EMBI),
        "tc":     stats.log_dif(df["tc_mayorista"]),
    }).dropna()
    out = {}
    for nombre, (desde, hasta) in REGIMENES_LARGO.items():
        s = v.loc[desde:hasta]
        if len(s) < 120:
            continue
        out[nombre] = {"granger": ec.granger_robusto(s, PARES_LARGO), "n": len(s),
                       "desde": s.index[0], "hasta": s.index[-1],
                       "sd_riesgo": float(s["riesgo"].std()),
                       "sd_tc": float(s["tc"].std())}
    return out, len(v), v.index[0], v.index[-1]


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

    with st.container(border=True):
        # El dossier recibe `banda`, `ordenes` y `pt` —los mismos objetos que alimentan
        # los gráficos de arriba— y no vuelve a estimar: la lectura describe exactamente
        # lo que está en pantalla. La tabla de Granger, en cambio, NO entra al dossier:
        # su "p mínimo sobre 6 rezagos" no es un p-valor. Ver platec/narrador.py.
        panel_narrador(lambda: nar.dossier_canal(
            banda, ordenes, shock="TC mayorista", respuesta="IPC", pt=pt,
            etiquetas=ETIQUETA, desde=anio),
            clave=f"canal_tc_ipc_{anio}",
            titulo="Lectura del analista — traslado del dólar a precios")

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

    with st.container(border=True):
        panel_narrador(lambda: nar.dossier_canal(
            banda_riesgo, ordenes_riesgo, shock="Riesgo país",
            respuesta="EMAE (desest.)", etiquetas=ETIQUETA, desde=anio),
            clave=f"canal_riesgo_emae_{anio}",
            titulo="Lectura del analista — riesgo soberano y actividad")

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
    seccion("El mismo sistema, once años más atrás")
    largo, n_largo, l0, l1 = _var_largo()
    st.caption(
        f"Sacando la brecha del sistema se pierde una variable y se ganan **once años**: "
        f"el CCL arranca en 2013 y el TC mayorista en marzo de 2002. El sistema bivariado "
        f"`[riesgo país, TC mayorista]` cubre **{n_largo:,} días** ({l0.date()} a "
        f"{l1.date()}) e incluye el default, el canje de 2005 y la crisis de 2008 — "
        f"episodios de crisis reales que la muestra desde 2013 no contiene. "
        f"**No arranca en 1999** aunque el riesgo país sí: durante la convertibilidad el "
        f"peso estaba fijo por ley y no hay tipo de cambio que modelar.")

    with st.container(border=True):
        filas = []
        for nombre, r in largo.items():
            g = r["granger"]
            fila = {"régimen": nombre, "días": r["n"],
                    "sd riesgo": round(r["sd_riesgo"], 2), "sd TC": round(r["sd_tc"], 2)}
            for rel in g.index:
                fila[rel] = ("✅ " if g.loc[rel, "robusta"] else "— ") + g.loc[rel, "signif. en"]
            filas.append(fila)
        st.dataframe(pd.DataFrame(filas).set_index("régimen"), **ANCHO)
        st.caption(
            "Mismo criterio que arriba: ✅ sólo si la relación aguanta los seis rezagos "
            "de la grilla. La columna `sd TC` explica sola el régimen de normalización: "
            "con el peso casi fijo entre 2005 y 2011 apenas hay variación cambiaria que "
            "pueda anticipar nada.")

    with st.container(border=True):
        st.markdown("**Qué agrega la muestra larga**")
        st.markdown(
            "**La hipótesis del riesgo país no se cae por falta de datos.** `Riesgo país "
            "→ TC` no es robusta en **ninguno** de los seis regímenes, y ahora eso "
            "incluye el default, la salida del default y 2008. Si el canal existiera "
            "en las crisis, once años más de muestra con tres crisis adentro deberían "
            "haberlo mostrado.\n\n"
            "**La dirección contraria aparece en un solo régimen: Cepo II.** `TC → riesgo "
            "país` aguanta los seis rezagos ahí y en ningún otro lado. La lectura "
            "económica es que bajo cepo duro el tipo de cambio oficial es una **variable "
            "de política**, y moverlo informa sobre la voluntad o la capacidad del "
            "gobierno de sostener el régimen — que es exactamente lo que el riesgo "
            "soberano pone precio. Sin cepo, el TC es un precio de mercado que absorbe "
            "esa información en simultáneo, y por eso no lidera.")
        st.info(
            "**Los dos sistemas coinciden.** El bivariado largo (2002-hoy) y el "
            "trivariado corto (2013-hoy) dan lo mismo: `TC → riesgo país` robusta sólo "
            "en Cepo II. Son muestras y especificaciones distintas, así que no es una "
            "verificación redundante.")

    with st.container(border=True):
        st.markdown("**Un artefacto que había que sacar antes de mirar nada**")
        st.markdown(
            "El EMBI+ tiene días en que cambia porque cambió **qué mide**: al liquidarse "
            "un canje los bonos en default salen del índice y entran los nuevos. El "
            "13/06/2005 el riesgo país pasa de 6.606 a 794 puntos en una rueda, y el "
            "10/09/2020 de 2.120 a 1.101. En log-diferencias son retornos de −212% y "
            "−65% que no son movimientos de precio.\n\n"
            "**No alcanza un filtro de outliers.** El 12/08/2019 —el lunes post-PASO— el "
            "riesgo país salta +52%: estadísticamente es igual de extremo y es el dato "
            "más informativo de la serie. Una regla por z-score borraría los dos. Las "
            "fechas se listan a mano con el evento que las justifica, igual que el tramo "
            "INTERVENIDO del IPC.")
        st.warning(
            "**Esto corrigió un resultado que ya estaba publicado.** En la muestra desde "
            "2013 el día del canje 2020 aportaba el **13% de la suma de cuadrados** de "
            "los retornos del riesgo país. Sin anularlo, `TC → riesgo país` en Cepo II se "
            "leía como frágil (4/6); anulándolo es robusta (6/6). El artefacto tapaba una "
            "relación real, no inventaba una falsa.")

    st.divider()
    seccion("¿La muestra es un régimen o varios?")
    tests, pot_general, pot_puntual = _estabilidad(anio)
    e1, e2 = st.columns([3, 2])
    with e1, st.container(border=True):
        st.markdown("**Sup-Wald por ecuación** · p-valor por bootstrap de regresores fijos")
        tabla = pd.DataFrame([{
            "ecuación": ETIQUETA[r.ecuacion], "supW": round(r.sup_wald, 2),
            "crítico 5%": round(r.critico_5, 2), "p": round(r.p_valor, 3),
            "máximo en": str(r.fecha_quiebre)[:7],
            "veredicto": "⚠ rechaza" if r.rechaza else "— no rechaza",
        } for r in tests]).set_index("ecuación")
        st.dataframe(tabla, **ANCHO)
        st.caption(
            "**No se parte la muestra: no se puede.** Son ~110 meses y once parámetros por "
            "ecuación; el corte de dic-23 dejaría 30 meses de un lado. Estimar por régimen "
            "es lo que la frecuencia diaria permite y la mensual no, así que acá se testea "
            "si el pooleo se sostiene. Sup-Wald y no Chow porque la fecha no se conoce de "
            "antemano, y elegirla mirando los datos invalida los valores críticos de tabla.")
    with e2, st.container(border=True):
        st.subheader("Dónde ponen el quiebre")
        st.markdown(
            "Ninguna ecuación rechaza. Pero mirá **dónde** cada una pone su máximo: el tipo "
            "de cambio y el IPC, los dos en **diciembre de 2023**; la actividad y el riesgo "
            "país, en **abril-mayo de 2020**.\n\n"
            "El test ubica los quiebres donde la historia dice que están —la devaluación y "
            "la pandemia— pero el estadístico no llega al umbral.")

    with st.container(border=True):
        st.markdown("**Y ahora la parte incómoda: ¿qué podía detectar este test?**")
        pc1, pc2 = st.columns(2)
        for col, pot, titulo, unidad in (
                (pc1, pot_general, "Quiebre en TODAS las pendientes", "pendientes ×"),
                (pc2, pot_puntual, "Quiebre SOLO en el pass-through", "e.e. en tc_l1")):
            with col:
                st.markdown(f"*{titulo}*")
                fig = go.Figure(go.Bar(
                    x=[f"{1 + s:.1f}" if "pendientes" in unidad else f"{s:.0f}"
                       for s in pot["tamaño"]],
                    y=pot["potencia"] * 100,
                    marker=dict(color=PALETA[0] if "TODAS" in titulo else PALETA[1]),
                    text=[f"{v:.0%}" for v in pot["potencia"]], textposition="outside",
                    textfont=dict(color="#cbd5e1", size=11),
                    hovertemplate="%{x}<br>potencia %{y:.0f}%<extra></extra>"))
                fig.add_hline(y=5, line=dict(color=COLOR["gris"], width=1, dash="dot"),
                              annotation_text="tamaño del test (5%)",
                              annotation_font=dict(size=9, color=COLOR["gris"]))
                _estilo(fig, height=230, leyenda=False)
                fig.update_layout(yaxis_title="potencia (%)", xaxis_title=unidad,
                                  margin=dict(t=20, b=24, l=8, r=8))
                fig.update_yaxes(range=[0, 115])
                st.plotly_chart(fig, **ANCHO)
        st.caption(
            "**«No se rechaza» no significa nada sin esto.** El sup-Wald prueba un quiebre en "
            "los once coeficientes a la vez: gasta todos los grados de libertad del modelo "
            "para detectar un movimiento en uno solo. Contra un cambio de régimen completo ve "
            "muy bien —duplicar las pendientes se detecta casi siempre— y contra un cambio en "
            "el pass-through, casi nada: haría falta un salto de treinta errores estándar, "
            "que ya no es un quiebre sino otra economía.")
        st.info(
            "**Qué se puede afirmar.** Se descarta un cambio de régimen generalizado. **No** "
            "se descarta un cambio en el pass-through en particular, que es justo el "
            "parámetro del que dependen las IRF de arriba — así que sus bandas siguen sin "
            "incorporar incertidumbre de régimen. No por falta de test, sino porque con ~110 "
            "meses ese test no existe. El camino para cerrarlo es más datos, no mejor método.")

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

    with st.container(border=True):
        panel_narrador(lambda: nar.dossier_nowcast(nc, nc_now, infl_real, ph=ph, desde=anio),
                       clave=f"nowcast_{anio}",
                       titulo="Lectura del analista — nowcast y curva de Phillips")


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

    with st.container(border=True):
        # Se le pasa el resumen YA calculado, no el nombre de la métrica: así el
        # dossier describe exactamente los números del gráfico de arriba.
        panel_narrador(lambda: nar.dossier_gobierno(vista, resumen_gob, unidad, como),
                       clave=f"gob_{vista}",
                       titulo=f"Lectura comparativa — {vista}")

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
# Página: Comercio espejo
# ---------------------------------------------------------------------------
# Los dos canales usan PALETA en ORDEN FIJO (slot 0 = exportador, slot 1 =
# importador) y no un color por ranking: si mañana se filtra un canal, el que
# queda conserva su color. El signo NO se codifica con color —eso chocaría con la
# identidad del canal— sino con la posición respecto del cero, que es una señal
# más fuerte. Verde y rojo quedan reservados para la semántica alza/baja del resto
# del dashboard y no se usan acá como identidad.
CANAL_COLOR = {"exportador": PALETA[0], "importador": PALETA[1]}
CANAL_NOMBRE = {"exportador": "Exportador (subfacturar exportaciones)",
                "importador": "Importador (sobrefacturar importaciones)"}

# Los mismos cortes de régimen que usa el VAR diario, para leer la serie contra el
# cepo en vez de contra el calendario.
CEPOS = [("Cepo I", 2011.5, 2015.9), ("Cepo II", 2019.7, 2023.9)]


@st.cache_data(ttl=3600, show_spinner="Cargando el panel de comercio espejo...")
def _espejo(desde: int):
    from platec import comercio_espejo as ce

    agregado = ce.por_anio(desde=desde)
    factores = ce.factores_cif_fob()
    detalle = ce.discrepancia(desde=desde)
    return agregado, factores, float(ce.factor_global()), detalle


@st.cache_data(ttl=3600, show_spinner="Estimando el contraste contra la brecha (bootstrap)...")
def _contraste(fuente: str, solo_reportado: bool):
    from platec import comercio_espejo as ce

    out = {}
    for canal in ("exportador", "importador"):
        try:
            out[canal] = ce.contraste_brecha(canal, fuente=fuente,
                                             solo_reportado=solo_reportado, repl=999)
        except ValueError:
            pass
    return out, ce.brecha_anual(fuente)


def _bandas_cepo(fig: go.Figure) -> go.Figure:
    """Sombreado de los períodos con control de cambios."""
    for nombre, x0, x1 in CEPOS:
        fig.add_vrect(x0=x0, x1=x1, fillcolor="rgba(255,255,255,.05)",
                      line_width=0, layer="below",
                      annotation_text=nombre, annotation_position="top left",
                      annotation_font=dict(size=10, color="#94a3b8"))
    return fig


def pagina_espejo():
    st.markdown(
        '<div class="hero"><h1>🌐 Comercio espejo</h1>'
        '<p>Lo que Argentina declara comerciar contra lo que declara la contraparte · '
        'detalle en docs/comercio_espejo.md</p></div>', unsafe_allow_html=True)

    c_a, c_b = st.columns([2, 1])
    desde = c_a.select_slider("Desde", list(range(1995, 2021, 5)), value=2005)
    fuente = c_b.selectbox("Brecha de referencia", ["blue", "ccl"],
                           help="El blue arranca en 2011 y el CCL en 2013: dos años más "
                                "de muestra, que sobre quince no es un detalle.")

    agregado, factores, f_global, detalle = _espejo(desde)
    if agregado.empty:
        st.warning("No hay panel de comercio espejo en la base. "
                   "Correr `python3 scripts/ingest_comtrade.py`.")
        return

    # El titular va sobre el último año COMPLETO, no sobre el último a secas: Comtrade
    # publica con rezago y en los últimos años faltan países, no falta comercio. En 2025
    # se aparean 51 socios contra ~70, y con ese cuarto faltante el agregado cambia de
    # signo. Los años provisorios se muestran igual, pero marcados.
    # `provisorio` viene por (año, canal), así que un año es completo solo si lo es en
    # TODOS sus canales: 2025 aparea bien en el importador y mal en el exportador, y
    # tomarlo como completo por el canal bueno lo dejaría a la vez adentro y afuera.
    por_anio_prov = agregado.groupby("anio")["provisorio"].any()
    completos = por_anio_prov[~por_anio_prov].index
    ultimo = int(max(completos)) if len(completos) else int(agregado["anio"].max())
    provisorios = sorted(int(a) for a in por_anio_prov[por_anio_prov].index)
    fila_ult = {r["canal"]: r for _, r in agregado[agregado["anio"] == ultimo].iterrows()}

    # --- KPIs -------------------------------------------------------------
    seccion(f"Discrepancia en {ultimo}")
    k = st.columns(3)
    for col, canal in zip(k, ("exportador", "importador")):
        r = fila_ult.get(canal)
        with col, st.container(border=True):
            st.markdown(f"**{CANAL_NOMBRE[canal].split(' (')[0]}**")
            if r is None:
                st.caption("sin dato")
                continue
            st.metric("Discrepancia", f"{r['gap']:,.0f} M USD",
                      f"{r['gap_pct']:+.1f}% del comercio del canal", delta_color="off")
            st.caption(f"{int(r['socios'])} socios apareados · "
                       f"{r['cobertura_fob']:.0%} del valor con FOB reportado")
    with k[2], st.container(border=True):
        st.markdown("**Ajuste CIF/FOB**")
        st.metric("Factor global estimado", f"+{(f_global - 1) * 100:.1f}%",
                  "la literatura supone +10% fijo", delta_color="off")
        st.caption("Es flete y seguro. Se calcula de los países que informan las dos "
                   "valoraciones; no se supone.")

    st.caption("**Signo:** en los dos canales, positivo = salida de divisas. Sacar dólares "
               "es declarar *de menos* al exportar y *de más* al importar, así que cada "
               "canal lleva su propia orientación.")
    if provisorios:
        st.info(
            f"El titular es {ultimo}, el último año **completo**. "
            f"{', '.join(str(a) for a in provisorios)} "
            f"{'está' if len(provisorios) == 1 else 'están'} marcado"
            f"{'' if len(provisorios) == 1 else 's'} como provisorio"
            f"{'' if len(provisorios) == 1 else 's'}: Comtrade publica con alrededor de un "
            "año de rezago y ahí todavía faltan países reportando. Falta comercio "
            "declarado, no hay menos comercio — el agregado de esos años puede incluso "
            "cambiar de signo.")

    # --- Serie anual ------------------------------------------------------
    st.divider()
    seccion("La discrepancia año a año")
    with st.container(border=True):
        fig = go.Figure()
        for canal in ("exportador", "importador"):
            sub = agregado[agregado["canal"] == canal]
            # Los años provisorios se rayan además de aclararse: la textura sobrevive
            # a la impresión en blanco y negro y a cualquier daltonismo, la opacidad no.
            fig.add_trace(go.Bar(
                x=sub["anio"], y=sub["gap"],
                name=CANAL_NOMBRE[canal].split(" (")[0],
                marker=dict(
                    color=CANAL_COLOR[canal],
                    opacity=[0.45 if pv else 1.0 for pv in sub["provisorio"]],
                    pattern=dict(shape=["/" if pv else "" for pv in sub["provisorio"]],
                                 solidity=0.35, fgcolor="#0b1220")),
                customdata=np.where(sub["provisorio"], " · provisorio", ""),
                hovertemplate="%{x}%{customdata}<br>%{y:,.0f} M USD<extra></extra>"))
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,.28)", width=1))
        _bandas_cepo(fig)
        _estilo(fig, height=380, leyenda=True)
        _titulo(fig, "Discrepancia espejo por canal (millones de dólares)")
        fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.06,
                          yaxis_title="millones de dólares", xaxis_title=None)
        st.plotly_chart(fig, **ANCHO)
        st.caption(
            "Las bandas sombreadas son los períodos con control de cambios. La escala es "
            "el nivel en dólares, así que parte del movimiento es el tamaño del comercio: "
            "el contraste de más abajo usa la discrepancia como **porcentaje** del comercio "
            "de cada par, que es lo comparable entre años. Las barras **rayadas y claras** "
            "son años provisorios: todavía faltan países por reportar.")

    # --- El ajuste CIF/FOB ------------------------------------------------
    st.divider()
    seccion("El ajuste que decide la medición")
    c1, c2 = st.columns([3, 2])
    with c1, st.container(border=True):
        principales = [c for c in (76, 152, 858, 68, 600, 842, 156, 276, 724, 380,
                                   392, 410, 528, 36) if c in factores.index]
        from platec import comercio_espejo as ce
        f = (pd.Series({ce.nombre_socio(c): (factores[c] - 1) * 100 for c in principales})
             .sort_values())
        fig = go.Figure(go.Bar(
            x=f.values, y=f.index, orientation="h",
            marker=dict(color=PALETA[0]),
            text=[f"{v:+.1f}%" for v in f.values], textposition="outside",
            textfont=dict(color="#cbd5e1", size=11),
            hovertemplate="%{y}: %{x:+.1f}%<extra></extra>"))
        fig.add_vline(x=10, line=dict(color=COLOR["ambar"], width=1.5, dash="dot"),
                      annotation_text="supuesto de la literatura (+10%)",
                      annotation_position="top",
                      annotation_font=dict(size=10, color=COLOR["ambar"]))
        _estilo(fig, height=430, leyenda=False)
        _titulo(fig, "Factor CIF/FOB estimado por país declarante")
        fig.update_layout(xaxis_title="flete y seguro sobre el valor FOB (%)",
                          yaxis_title=None)
        fig.update_xaxes(range=[0, max(14, float(f.max()) * 1.35)])
        st.plotly_chart(fig, **ANCHO)
    with c2, st.container(border=True):
        st.subheader("Por qué no es un 10% fijo")
        st.markdown(
            "El flete **es distancia**. Los vecinos con frontera terrestre están en un "
            "dígito bajo y los socios del otro lado del mundo, en dos dígitos.\n\n"
            "Aplicarle el 10% canónico a Brasil **sobrecorrige seis puntos y puede dar "
            "vuelta el signo** de la discrepancia: convierte una subfacturación en un "
            "superávit espejo que no existe.\n\n"
            "Acá el factor se estima con la mediana de los años en que cada país informa "
            "las dos valoraciones. Cuando nunca las informa, recién ahí se usa la mediana "
            "global — que también se calcula.")
        st.caption("Un cociente CIF/FOB fuera de [1,0 ; 1,5] se descarta: en los datos de "
                   "2022 hay un registro con 9.993%, que es un error de reporte y no un "
                   "flete. Sin acotarlo, un solo registro corre la mediana de un país.")

    # --- El contraste -----------------------------------------------------
    st.divider()
    seccion("¿La discrepancia responde al precio del arbitraje?")
    solo_rep = st.checkbox(
        "Usar solo los pares sin ninguna imputación CIF/FOB", value=False,
        help="Deja únicamente los pares en los que AMBOS lados informaron su propio FOB. "
             "Si el resultado sobrevive ahí, no es un artefacto del ajuste.")
    contrastes, brecha = _contraste(fuente, solo_rep)

    if not contrastes:
        st.info("Muestra insuficiente para el contraste con esta selección.")
    else:
        cc1, cc2 = st.columns([3, 2])
        with cc1, st.container(border=True):
            d = detalle.copy()
            d["brecha"] = d["anio"].map(brecha)
            d = d.dropna(subset=["brecha"])
            fig = go.Figure()
            for canal in ("exportador", "importador"):
                sub = d[d["canal"] == canal]
                if sub.empty:
                    continue
                por_anio = sub.groupby("anio").agg(
                    brecha=("brecha", "first"),
                    gap_pct=("gap_pct", "median")).reset_index()
                fig.add_trace(go.Scatter(
                    x=por_anio["brecha"], y=por_anio["gap_pct"], mode="markers",
                    name=CANAL_NOMBRE[canal].split(" (")[0],
                    marker=dict(size=11, color=CANAL_COLOR[canal],
                                line=dict(width=2, color="#0b1220")),
                    customdata=por_anio["anio"],
                    hovertemplate="%{customdata}<br>brecha %{x:.0f}%<br>"
                                  "discrepancia %{y:+.1f}%<extra></extra>"))
                r = contrastes.get(canal)
                if r is not None:
                    xs = np.linspace(por_anio["brecha"].min(), por_anio["brecha"].max(), 2)
                    centro = por_anio["gap_pct"].mean() - r["beta"] * por_anio["brecha"].mean()
                    fig.add_trace(go.Scatter(
                        x=xs, y=centro + r["beta"] * xs, mode="lines",
                        line=dict(color=CANAL_COLOR[canal], width=2,
                                  dash="solid" if r["p_wcb"] < 0.10 else "dot"),
                        showlegend=False, hoverinfo="skip"))
            fig.add_hline(y=0, line=dict(color="rgba(255,255,255,.28)", width=1))
            _estilo(fig, height=400, leyenda=True)
            _titulo(fig, "Discrepancia mediana del año contra brecha cambiaria")
            fig.update_layout(xaxis_title="brecha cambiaria promedio del año (%)",
                              yaxis_title="discrepancia (% del comercio del par)")
            st.plotly_chart(fig, **ANCHO)
            st.caption(
                "Cada punto es un año. La recta es la pendiente estimada en el panel "
                "completo (no sobre estas medianas): **llena** si el efecto pasa el "
                "bootstrap al 10%, **punteada** si no. Los puntos son medianas por año "
                "solo para que el gráfico sea legible.")
        with cc2, st.container(border=True):
            st.subheader("Panel con efectos fijos")
            for canal, r in contrastes.items():
                signif = r["p_wcb"] < 0.05
                st.metric(f"β · canal {canal}", f"{r['beta']:+.4f}",
                          f"p={r['p_wcb']:.3f} ({'significativo' if signif else 'no significativo'})",
                          delta_color="off")
                st.caption(f"se={r['se']:.4f} · n={r['n']:,} · {r['unidades']} socios · "
                           f"{r['anios']} años")
            st.markdown(
                "**β** = puntos porcentuales de discrepancia por cada punto de brecha. "
                "Pasar de brecha nula a 100% agrega "
                f"**{contrastes['exportador']['beta'] * 100:.1f} pp** en el canal exportador.")

        with st.container(border=True):
            st.markdown("**La asimetría es el hallazgo**")
            st.markdown(
                "La lectura habitual pone el foco en la **sobrefacturación de "
                "importaciones**. Los datos dicen lo contrario: ese canal no responde a la "
                "brecha y el exportador sí.\n\n"
                "Tiene una explicación institucional directa: **sobrefacturar una "
                "importación exige acceso al dólar oficial**, que es justamente lo que el "
                "cepo raciona vía DJAI, SIMI o SIRA. **Subfacturar una exportación no exige "
                "permiso de nadie**: alcanza con dejar la diferencia afuera. El canal que "
                "escala con el premio del arbitraje es el que no necesita autorización.\n\n"
                "El control de cambios no elimina el arbitraje: lo empuja hacia el lado "
                "que no controla.")
            st.caption(
                "**Qué no prueba.** No hay identificación causal: los años de brecha alta "
                "son también años de crisis y controles. Quince clusters son pocos incluso "
                "con bootstrap, así que un p entre 0,03 y 0,06 es sugerente y no "
                "concluyente. Y sigue siendo una *discrepancia*: reexportaciones, timing y "
                "clasificación no se corrigen.")

    # --- Detalle por socio ------------------------------------------------
    st.divider()
    seccion("Por socio")
    anio_sel = st.select_slider("Año", sorted(detalle["anio"].unique()), value=ultimo)
    sub = detalle[detalle["anio"] == anio_sel].copy()
    with st.container(border=True):
        sub["Argentina declara"] = (sub["ar_declara"] / 1e6).round(0)
        sub["El socio declara"] = (sub["socio_declara"] / 1e6).round(0)
        sub["Discrepancia"] = (sub["gap"] / 1e6).round(0)
        sub["%"] = sub["gap_pct"].round(1)
        sub["FOB del socio"] = sub["origen_socio"]
        tabla_socios = (sub[["socio", "canal", "Argentina declara", "El socio declara",
                             "Discrepancia", "%", "FOB del socio"]]
                        .sort_values("Discrepancia", key=abs, ascending=False)
                        .rename(columns={"socio": "Socio", "canal": "Canal"}))
        st.dataframe(tabla_socios.head(30), **ANCHO, hide_index=True)
        st.caption(
            "En millones de dólares, ambos lados llevados a FOB. **FOB del socio** dice si "
            "esa cifra es la que reportó el país o una imputada con el factor: una "
            "discrepancia grande sobre un valor imputado pesa menos que una sobre dos "
            "cifras reportadas. Se excluyen los pares que comercian menos de 50 millones "
            "al año, donde un solo embarque a caballo del cierre distorsiona el porcentaje.")

    # --- Lectura del analista --------------------------------------------
    if contrastes:
        st.divider()
        with st.container(border=True):
            panel_narrador(
                lambda: nar.dossier_espejo(
                    {c: fila_ult[c] for c in fila_ult},
                    contrastes, f_global,
                    int(detalle[detalle["anio"] == ultimo]["socio_code"].nunique())),
                clave=f"espejo_{desde}_{fuente}_{solo_rep}",
                titulo="Lectura del analista — comercio espejo y brecha")

# ---------------------------------------------------------------------------
# Página: Firmas sintéticas
# ---------------------------------------------------------------------------
# ÚNICA PÁGINA DEL DASHBOARD QUE NO MUESTRA DATOS REALES. Todo lo que hay acá lo
# generó `platec.firmas_sinteticas` a partir de una semilla. Por eso el aviso va
# arriba de todo y no al pie: en una plataforma cuyo valor es que no inventa
# números, la excepción tiene que anunciarse antes de que alguien lea una cifra.
@st.cache_data(ttl=3600, show_spinner="Entrenando y evaluando el detector...")
def _deteccion(n: int, ejercicios: int, semilla: int, prevalencia: float, brecha: float):
    from platec import deteccion as det
    from platec import firmas_sinteticas as fs

    df = fs.generar(n_firmas=n, ejercicios=ejercicios, semilla=semilla,
                    prevalencia=prevalencia, brecha=brecha)
    return det.evaluar(df, fs.calibraciones())


@st.cache_data(ttl=3600, show_spinner="Generando el panel sintético...")
def _firmas(n: int, ejercicios: int, semilla: int, prevalencia: float, brecha: float):
    from platec import firmas_sinteticas as fs

    df = fs.generar(n_firmas=n, ejercicios=ejercicios, semilla=semilla,
                    prevalencia=prevalencia, brecha=brecha)
    return (df, fs.articula(df), fs.desvio_benford(df["ingresos"]),
            fs.discrepancia_exportadora(df), fs.calibraciones())


def pagina_firmas():
    from platec import firmas_sinteticas as fs

    st.markdown(
        '<div class="hero"><h1>🧪 Firmas sintéticas</h1>'
        '<p>Estados contables generados para investigación de detección · '
        'detalle en docs/firmas_sinteticas.md</p></div>', unsafe_allow_html=True)
    st.error(
        "**Nada de esta página es un dato real.** Son empresas ficticias generadas por "
        "`platec.firmas_sinteticas` a partir de una semilla, con etiqueta de verdad sobre "
        "qué firma ejecuta qué maniobra. No representan a ninguna empresa existente y no "
        "se persiste ninguna fila: cambiar la semilla cambia el panel entero. Lo único "
        "real que hay acá es la estructura sectorial del INDEC contra la que se calibra.")

    c1, c2, c3, c4 = st.columns(4)
    n = c1.select_slider("Firmas", [200, 500, 1000, 2000], value=500)
    prevalencia = c2.select_slider("Prevalencia", [0.01, 0.02, 0.05, 0.20, 0.40, 0.65],
                                   value=0.02, format_func=lambda v: f"{v:.0%}")
    brecha = c3.select_slider("Brecha cambiaria", [0, 25, 50, 100, 150], value=100,
                              format_func=lambda v: f"{v}%")
    semilla = c4.number_input("Semilla", min_value=0, max_value=9999, value=7, step=1)

    df, articula, benford, disc, cals = _firmas(n, 4, int(semilla), prevalencia, float(brecha))

    seccion("Que el dataset no sea trivial")
    k = st.columns(4)
    with k[0], st.container(border=True):
        st.metric("Articulación contable", "✅ cierra" if articula else "❌ ROTA")
        st.caption("Activo = Pasivo + Patrimonio en todas las filas. Si no cierra, un "
                   "detector encuentra la maniobra por la vía equivocada.")
    with k[1], st.container(border=True):
        st.metric("Desvío de Benford", f"{benford:.4f}",
                  "conformidad < 0,006" if benford < 0.006 else "aceptable < 0,015",
                  delta_color="off")
        st.caption("Los montos salen de una lognormal. Con `uniform()` el problema se "
                   "vuelve trivial: la desviación de Benford ya es un detector forense.")
    with k[2], st.container(border=True):
        marcadas = df.groupby("firma")["tipologia"].first().ne("limpia").mean()
        st.metric("Firmas con maniobra", f"{marcadas:.1%}")
        st.caption("En AML la prevalencia real es del orden de 1 en 1.000. Un dataset "
                   "balanceado es un problema de clasificación fácil, no de detección.")
    with k[3], st.container(border=True):
        objetivo = df.attrs["objetivo_discrepancia"]
        st.metric("Discrepancia exportadora", f"{disc:.4f}",
                  (("✅ " if df.attrs["calibrado"] else "⚠ ") + f"objetivo {objetivo:.4f}")
                  if brecha else "sin calibrar", delta_color="off")
        st.caption("Calibrada contra el β que la plataforma estimó sobre datos reales "
                   "en el módulo de comercio espejo.")

    if brecha and not df.attrs["calibrado"]:
        minimo = fs.share_exportador_minimo(float(brecha))
        st.info(
            f"**La calibración no es factible con esta prevalencia, y no es un bug del "
            f"generador: es una restricción del propio β.** Para omitir el "
            f"{objetivo:.1%} de las exportaciones sin que ninguna firma omita más del "
            f"{fs.INTENSIDAD_MAXIMA:.0%} de las suyas, hace falta que al menos el "
            f"**{minimo:.1%} del valor exportado** esté en manos de manipuladores. Con "
            f"prevalencia {prevalencia:.0%} no llegan a tanto. Subila y mirá cómo el "
            f"logrado alcanza al objetivo justo cuando cruza ese umbral.\n\n"
            f"Dicho de otro modo: **el β estimado sobre datos reales implica cuánto "
            f"comercio tiene que estar comprometido** para que la discrepancia observada "
            f"exista. Eso es un resultado, no un parámetro.")

    st.divider()
    seccion("Qué deja cada maniobra en los libros")
    with st.container(border=True):
        limpias = df[~df["maniobra_activa"]]
        esp_m = lambda s: s["sector"].map(lambda x: cals[x].margen_operativo)   # noqa: E731
        esp_s = lambda s: s["sector"].map(lambda x: cals[x].participacion_salarial)  # noqa: E731

        # El crecimiento máximo es de la TRAYECTORIA de cada firma: sin esa columna,
        # la entidad reactivada es indistinguible de una limpia y la tabla mentiría.
        crec = df.sort_values(["firma", "ejercicio"]).copy()
        crec["crec"] = crec.groupby("firma")["ingresos"].pct_change()
        maximo = crec.groupby(["firma", "tipologia"])["crec"].max()

        def perfil(s, etiqueta, tip):
            return {"tipología": etiqueta, "firmas": s["firma"].nunique(),
                    "margen op.": ((s["resultado_operativo"] / s["ingresos"]) / esp_m(s)).median(),
                    "nómina": ((s["salarios"] / s["ingresos"]) / esp_s(s)).median(),
                    "ing. / act. fijo": (s["ingresos"] / s["activo_fijo"]).median(),
                    "pasivo / patrim.": (s["pasivo"] / s["patrimonio"]).median(),
                    "caja / ingresos": (s["caja"] / s["ingresos"]).median(),
                    "import / costos": (s["importaciones"] / s["otros_costos"]).median(),
                    "crec. máx.": maximo.xs(tip, level="tipologia").median()}

        filas = [perfil(limpias, "(sin maniobra)", "limpia")]
        for tip in sorted(set(df["tipologia"]) - {"limpia"}):
            s = df[(df["tipologia"] == tip) & df["maniobra_activa"]]
            if not s.empty:
                filas.append(perfil(s, tip, tip))
        tabla = pd.DataFrame(filas).set_index("tipología")
        st.dataframe(tabla.style.format({
            "margen op.": "{:.2f}", "nómina": "{:.2f}", "ing. / act. fijo": "{:.2f}",
            "pasivo / patrim.": "{:.2f}", "caja / ingresos": "{:.3f}",
            "import / costos": "{:.3f}", "crec. máx.": "{:.0%}"}), **ANCHO)
        st.caption(
            "**Margen y nómina van normalizados por el sector de cada firma**: 1,00 es "
            "«igual a lo normal de su actividad». Sin esa normalización se compara "
            "Enseñanza (94% de nómina) contra Minas (29%) y no la maniobra. La "
            "estructura sectorial sale de la Cuenta de Generación del Ingreso del INDEC. "
            "**`crec. máx.` es el mayor salto interanual de facturación de la firma**: es "
            "una propiedad de la trayectoria, no del ejercicio.")

    with st.expander("De dónde sale cada tipología"):
        st.caption(
            "Cada maniobra cita el indicador que la respalda. Hay un test que verifica "
            "que ninguna exista sin fuente: si no puede citar nada, probablemente no "
            "exista. **De los 35 indicadores de GAFI, sólo unos siete son observables en "
            "un estado contable anual** — el 80% son de documentos aduaneros y de "
            "movimientos de cuenta, que un balance no contiene.")
        st.dataframe(pd.DataFrame(
            [{"tipología": k, "descripción": v.descripcion, "fuente": v.fuente}
             for k, v in fs.TIPOLOGIAS.items() if k != "limpia"]).set_index("tipología"),
            **ANCHO)

    c5, c6 = st.columns(2)
    with c5, st.container(border=True):
        st.subheader("Dos son deliberadamente difíciles")
        st.markdown(
            "La **fachada** conserva nómina y planta porque **son reales**: no hay "
            "anomalía estructural que buscar, sólo factura más de lo que esa capacidad "
            "explica. Un dataset con sólo pantallas sobreestima cualquier detector.\n\n"
            "La **entidad reactivada** es indistinguible en corte transversal — mirá su "
            "fila: margen y nómina normales. Su anomalía está en `crec. máx.`, o sea en "
            "la **trayectoria**. Obliga a usar la historia de la firma y no una foto.\n\n"
            "La **subfacturación** comprime el margen, pero eso lo comparte con "
            "cualquier empresa que simplemente gana poco: el estado contable la "
            "**señala y no la identifica**. Lo que la identifica es comparar contra lo "
            "que declara la contraparte — que es lo que hace el comercio espejo.")
    with c6, st.container(border=True):
        st.subheader("El puente con el resultado macro")
        st.markdown(
            f"La intensidad de la subfacturación se calibra para que la discrepancia "
            f"agregada reproduzca **β = {fs.BETA_EXPORTADOR:+.4f}** por punto de brecha, "
            f"que es lo que la plataforma estimó sobre datos reales.\n\n"
            "**La sobrefacturación no escala con la brecha, y eso es el hallazgo**, no "
            "una omisión: el contraste macro da β = +0,009 con p = 0,68, un cero limpio. "
            "Sobrefacturar exige acceso al dólar oficial, que es lo que el cepo raciona; "
            "subfacturar no exige permiso de nadie.")
        st.caption("Mové la brecha y mirá la métrica de discrepancia de arriba: sigue al "
                   "objetivo. La intensidad de la sobrefacturación no se mueve.")

    st.divider()
    seccion("El panel")
    with st.container(border=True):
        cols = ["firma", "sector", "ejercicio", "tipologia", "maniobra_activa",
                "ingresos", "salarios", "resultado_operativo", "activo",
                "pasivo", "patrimonio", "exportaciones", "importaciones"]
        solo = st.checkbox("Mostrar solo las firmas con maniobra", value=False)
        vista = df[df["tipologia"] != "limpia"] if solo else df
        st.dataframe(vista[cols].head(300), **ANCHO, hide_index=True)
        st.caption(f"{len(df):,} filas · {df['firma'].nunique():,} firmas · "
                   f"{df['sector'].nunique()} sectores · semilla {int(semilla)}. "
                   "Se muestran las primeras 300.")

    # --- el detector --------------------------------------------------------
    st.divider()
    seccion("El detector")
    try:
        ev = _deteccion(n, 4, int(semilla), prevalencia, float(brecha))
    except ValueError as e:
        st.info(f"No se puede evaluar con esta selección: {e}")
        ev = None

    if ev is not None:
        st.caption(
            "Características observables por firma —razones de un balance y un estado de "
            "resultados, normalizadas por sector— y validación cruzada. La unidad es la "
            "**firma** y no el ejercicio: se investiga una empresa, no su año fiscal 2022, "
            "y evaluar por ejercicio filtraría porque los otros años de la misma firma "
            "estarían en el entrenamiento.")
        if ev["positivas"] < 30:
            st.warning(
                f"**Sólo {ev['positivas']} firmas con maniobra en este panel: las métricas "
                f"de abajo son ruidosas.** No es que el detector ande peor — es que con "
                f"tan pocas positivas la validación cruzada estima mal. Subí el número de "
                f"firmas o la prevalencia para que el número signifique algo.")
        m = st.columns(4)
        with m[0], st.container(border=True):
            st.metric("PR-AUC", f"{ev['pr_auc']:.3f}", f"azar {ev['azar']:.3f}",
                      delta_color="off")
            st.caption("La métrica que corresponde bajo desbalance. **Su piso de azar es "
                       "la prevalencia, no 0,5.**")
        with m[1], st.container(border=True):
            st.metric("ROC-AUC", f"{ev['roc_auc']:.3f}", "exagera acá", delta_color="off")
            st.caption("Se informa porque todo el mundo lo pide. Se apoya en la tasa de "
                       "falsos positivos, y con tantos negativos esa tasa se mueve poco "
                       "**aunque las alertas sean casi todas falsas**.")
        with m[2], st.container(border=True):
            st.metric(f"Precisión @ {ev['presupuesto']}", f"{ev['precision_en_k']:.1%}")
            st.caption("La única operativamente honesta: de las k firmas alertadas, "
                       "cuántas manipulaban de verdad.")
        with m[3], st.container(border=True):
            st.metric("Exactitud", "no se informa")
            st.caption(f"Con prevalencia {ev['azar']:.0%}, predecir «todas limpias» acierta "
                       f"el {1 - ev['azar']:.0%}. No es conservadora: es inservible.")

        y = (df.groupby("firma")["tipologia"].first().ne("limpia").astype(int)
             .reindex(ev["puntajes"].index))
        d1, d2 = st.columns(2)
        with d1, st.container(border=True):
            orden = np.argsort(-ev["puntajes"].to_numpy())
            aciertos = np.cumsum(y.to_numpy()[orden])
            ks = np.arange(1, len(orden) + 1)
            tope = min(len(ks), max(ev["presupuesto"] * 6, 60))
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ks[:tope], y=(aciertos[:tope] / ks[:tope]) * 100,
                                     mode="lines", line=dict(width=2.4, color=PALETA[0]),
                                     name="precisión",
                                     hovertemplate="alertas %{x}<br>precisión %{y:.0f}%"
                                                   "<extra></extra>"))
            fig.add_hline(y=ev["azar"] * 100, line=dict(color=COLOR["gris"], width=1,
                                                        dash="dot"),
                          annotation_text="azar", annotation_position="bottom right",
                          annotation_font=dict(size=10, color=COLOR["gris"]))
            _estilo(fig, height=320, leyenda=False)
            _titulo(fig, "Precisión según el presupuesto de alertas")
            fig.update_layout(xaxis_title="firmas alertadas (k)",
                              yaxis_title="precisión (%)")
            st.plotly_chart(fig, **ANCHO)
            st.caption("Un equipo investiga k casos por período. La curva dice qué "
                       "fracción de esas k alertas sería real: cae a medida que se baja "
                       "en el ranking, y eso es lo que decide cuánto trabajo se desperdicia.")
        with d2, st.container(border=True):
            rec = pd.Series(ev["recall_por_tipologia"]).sort_values()
            fig = go.Figure(go.Bar(
                x=rec.values * 100, y=[i.replace("_", " ") for i in rec.index],
                orientation="h", marker=dict(color=PALETA[0]),
                text=[f"{v:.0%}" for v in rec.values], textposition="outside",
                textfont=dict(color="#cbd5e1", size=11),
                hovertemplate="%{y}: %{x:.0f}%<extra></extra>"))
            _estilo(fig, height=320, leyenda=False)
            _titulo(fig, f"Recall por tipología, con {ev['presupuesto']} alertas")
            fig.update_layout(xaxis_title="detectadas (%)", yaxis_title=None)
            fig.update_xaxes(range=[0, 118])
            st.plotly_chart(fig, **ANCHO)
            st.caption("Qué maniobra se ve y cuál no. Es la lectura más útil del "
                       "detector: el promedio esconde que una tipología puede estar "
                       "en cero.")

        with st.container(border=True):
            st.markdown("**Lo que el detector encontró, y no fue una maniobra**")
            st.markdown(
                "La primera corrida dio **PR-AUC 0,89 con prevalencia 2%**: demasiado "
                "bueno para un problema de AML. La causa estaba en el generador. La "
                "intensidad exportadora de las firmas limpias se sorteaba en "
                "[0,00 – 0,35] y la de las subfacturadoras en [0,45 – 0,85] — **soportes "
                "disjuntos**, así que `exportador > 0,40` las identificaba perfecto. El "
                "clasificador aprendía a reconocer el sorteo, no la maniobra.\n\n"
                "Corregido —ahora las limpias también comercian y las manipuladoras "
                "salen de esa misma población— el PR-AUC bajó a 0,785. **Un detector que "
                "anda demasiado bien es un diagnóstico sobre el dataset, no un logro.**")
            st.info(
                "**La sobrefacturación de importaciones queda en cero, y es un "
                "resultado.** Aislada en su propio panel da PR-AUC 0,101 contra un azar "
                "de 0,030: detectable, pero apenas. La diferencia de margen contra las "
                "limpias vale **0,06 desvíos** de la dispersión natural de rentabilidad "
                "entre empresas — un margen comprimido lo comparte con cualquier empresa "
                "que simplemente gana poco. Es la confirmación cuantitativa de lo que el "
                "indicador de GAFI sugería: *«consistently displays unreasonably low "
                "profit margins»* es una señal real y **confundida**.")

    st.warning(
        "**Lo que este dataset NO prueba.** Un detector entrenado acá encuentra las "
        "maniobras que uno mismo inyectó: no dice nada sobre el lavado real. Sirve para "
        "comparar métodos entre sí, para medir potencia —cuán chica puede ser una "
        "maniobra y todavía detectarse— y para desarrollar el pipeline. No como "
        "evidencia sobre la economía argentina.")


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
st.sidebar.markdown("# 📊 Plataforma Económica")
st.sidebar.caption("Monitoreo · Análisis · Econometría")
st.sidebar.divider()
pagina = st.sidebar.radio(
    "Navegación", ["🏠  Cockpit", "🔎  Explorador", "🏛  Gobiernos", "🧮  Econometría",
                   "🌐  Comercio espejo", "🧪  Firmas sintéticas"],
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
elif "Econometría" in pagina:
    pagina_econometria()
elif "espejo" in pagina:
    pagina_espejo()
else:
    pagina_firmas()
