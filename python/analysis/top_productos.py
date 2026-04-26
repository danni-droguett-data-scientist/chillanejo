"""
top_productos.py — Análisis exploratorio: top 50-100 productos por ventas.

Lee desde Supabase (Capa 2). Nunca llama a Relbase directamente.

Salidas:
  - Tabla top_productos en consola
  - Archivo CSV: python/analysis/output/top_productos_YYYYMMDD.csv
  - Gráficos: barras de ingresos, scatter margen vs volumen

Uso:
  python python/analysis/top_productos.py
  python python/analysis/top_productos.py --top 100 --meses 6
  python python/analysis/top_productos.py --sin-graficos
"""

import os
import sys
import argparse
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] — %(message)s",
)
logger = logging.getLogger("analysis.top_productos")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

OUTPUT_DIR = Path(__file__).parent / "output"
TOP_DEFAULT = 50
MESES_DEFAULT = 18


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def _supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# Extracción desde Supabase
# ---------------------------------------------------------------------------

def cargar_detalle_ventas(supabase, desde_fecha: str) -> pd.DataFrame:
    """
    Lee ventas_detalle unida con ventas (para filtrar por fecha)
    y con productos (para obtener costo_unitario cuando falta en detalle).
    """
    logger.info("Cargando ventas_detalle desde %s...", desde_fecha)

    # ventas_detalle con fecha desde ventas y nombre desde productos
    resp = (
        supabase.table("ventas_detalle")
        .select(
            "codigo_producto, nombre_producto, cantidad, "
            "subtotal_neto, costo_unitario, "
            "ventas!inner(fecha_emision, estado, tipo_dte)"
        )
        .gte("ventas.fecha_emision", desde_fecha)
        # Solo ventas vigentes (excluye anuladas)
        .neq("ventas.estado", "anulado")
        .execute()
    )

    registros = resp.data or []
    if not registros:
        logger.warning("No se encontraron registros en ventas_detalle para el período.")
        return pd.DataFrame()

    filas = []
    for r in registros:
        venta = r.get("ventas") or {}
        filas.append(
            {
                "codigo_producto": r.get("codigo_producto"),
                "nombre_producto": r.get("nombre_producto"),
                "cantidad": r.get("cantidad") or 0,
                "subtotal_neto": r.get("subtotal_neto") or 0,
                "costo_unitario": r.get("costo_unitario"),
                "fecha_emision": venta.get("fecha_emision"),
                "tipo_dte": venta.get("tipo_dte"),
            }
        )

    df = pd.DataFrame(filas)
    df["fecha_emision"] = pd.to_datetime(df["fecha_emision"])
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0)
    df["subtotal_neto"] = pd.to_numeric(df["subtotal_neto"], errors="coerce").fillna(0)
    df["costo_unitario"] = pd.to_numeric(df["costo_unitario"], errors="coerce")

    logger.info("Registros cargados: %d líneas de detalle", len(df))
    return df


def cargar_costos_productos(supabase) -> pd.DataFrame:
    """Carga costo_unitario desde tabla productos como fallback."""
    resp = (
        supabase.table("productos")
        .select("codigo, costo_unitario")
        .not_.is_("costo_unitario", "null")
        .execute()
    )
    data = resp.data or []
    if not data:
        return pd.DataFrame(columns=["codigo", "costo_unitario"])
    return pd.DataFrame(data).rename(columns={"codigo": "codigo_producto"})


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------

def calcular_top_productos(
    df_detalle: pd.DataFrame,
    df_costos: pd.DataFrame,
    top_n: int = TOP_DEFAULT,
) -> pd.DataFrame:
    """
    Agrega por producto y calcula métricas clave.

    Columnas resultantes:
      codigo_producto, nombre_producto,
      unidades_vendidas, transacciones,
      ingresos_netos, costo_total,
      margen_bruto_neto, margen_pct,
      ticket_promedio, precio_promedio_neto,
      rank_ingresos, rank_unidades, rank_margen
    """
    if df_detalle.empty:
        return pd.DataFrame()

    # Rellena costo_unitario faltante desde tabla productos
    if not df_costos.empty:
        df_detalle = df_detalle.merge(
            df_costos.rename(columns={"costo_unitario": "costo_catalogo"}),
            on="codigo_producto",
            how="left",
        )
        mask_sin_costo = df_detalle["costo_unitario"].isna()
        df_detalle.loc[mask_sin_costo, "costo_unitario"] = df_detalle.loc[
            mask_sin_costo, "costo_catalogo"
        ]
        df_detalle = df_detalle.drop(columns=["costo_catalogo"], errors="ignore")

    # Costo total de cada línea
    df_detalle["costo_linea"] = df_detalle["costo_unitario"] * df_detalle["cantidad"]

    agg = (
        df_detalle.groupby(["codigo_producto", "nombre_producto"])
        .agg(
            unidades_vendidas=("cantidad", "sum"),
            transacciones=("subtotal_neto", "count"),
            ingresos_netos=("subtotal_neto", "sum"),
            costo_total=("costo_linea", "sum"),
        )
        .reset_index()
    )

    # Margen bruto (solo para productos con costo conocido)
    agg["margen_bruto_neto"] = np.where(
        agg["costo_total"] > 0,
        agg["ingresos_netos"] - agg["costo_total"],
        np.nan,
    )
    agg["margen_pct"] = np.where(
        (agg["ingresos_netos"] > 0) & agg["margen_bruto_neto"].notna(),
        (agg["margen_bruto_neto"] / agg["ingresos_netos"] * 100).round(1),
        np.nan,
    )

    # Precio promedio por unidad
    agg["precio_promedio_neto"] = np.where(
        agg["unidades_vendidas"] > 0,
        (agg["ingresos_netos"] / agg["unidades_vendidas"]).round(0),
        np.nan,
    )

    # Rankings
    agg["rank_ingresos"] = agg["ingresos_netos"].rank(ascending=False, method="min").astype(int)
    agg["rank_unidades"] = agg["unidades_vendidas"].rank(ascending=False, method="min").astype(int)
    agg["rank_margen"] = agg["margen_bruto_neto"].rank(ascending=False, method="min", na_option="bottom").astype(int)

    top = (
        agg.sort_values("ingresos_netos", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    top.index += 1  # ranking 1-based

    logger.info("Top %d productos calculados.", len(top))
    return top


# ---------------------------------------------------------------------------
# Insights adicionales
# ---------------------------------------------------------------------------

def resumen_ejecutivo(df_top: pd.DataFrame, df_detalle: pd.DataFrame) -> dict:
    """Genera métricas resumen del período."""
    if df_detalle.empty:
        return {}

    total_ingresos = df_detalle["subtotal_neto"].sum()
    ingresos_top = df_top["ingresos_netos"].sum() if not df_top.empty else 0

    return {
        "total_ingresos_netos": round(total_ingresos, 0),
        "ingresos_top_productos": round(ingresos_top, 0),
        "concentracion_pct": round(ingresos_top / total_ingresos * 100, 1) if total_ingresos else 0,
        "total_lineas_detalle": len(df_detalle),
        "productos_distintos": df_detalle["codigo_producto"].nunique(),
        "fecha_min": df_detalle["fecha_emision"].min().date().isoformat() if not df_detalle.empty else None,
        "fecha_max": df_detalle["fecha_emision"].max().date().isoformat() if not df_detalle.empty else None,
    }


def calcular_estacionalidad(df_detalle: pd.DataFrame, codigo_producto: str) -> pd.Series:
    """Ventas mensuales de un producto específico."""
    mask = df_detalle["codigo_producto"] == codigo_producto
    mensual = (
        df_detalle[mask]
        .groupby(df_detalle["fecha_emision"].dt.to_period("M"))["subtotal_neto"]
        .sum()
    )
    return mensual


# ---------------------------------------------------------------------------
# Visualizaciones (opcionales)
# ---------------------------------------------------------------------------

def generar_graficos(df_top: pd.DataFrame, output_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        logger.warning("matplotlib no disponible. Saltando gráficos.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    hoy = date.today().strftime("%Y%m%d")
    top20 = df_top.head(20)

    # Gráfico 1: Top 20 por ingresos netos
    fig, ax = plt.subplots(figsize=(12, 7))
    colores = ["#2563eb" if i < 10 else "#93c5fd" for i in range(len(top20))]
    ax.barh(
        top20["nombre_producto"].str[:40],
        top20["ingresos_netos"] / 1_000_000,
        color=colores,
    )
    ax.set_xlabel("Ingresos Netos (millones CLP)")
    ax.set_title("Top 20 Productos por Ingresos Netos")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.1fM"))
    plt.tight_layout()
    ruta = output_dir / f"top20_ingresos_{hoy}.png"
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    logger.info("Gráfico guardado: %s", ruta)

    # Gráfico 2: Scatter margen% vs ingresos (solo productos con margen conocido)
    df_margen = df_top.dropna(subset=["margen_pct"]).head(50)
    if not df_margen.empty:
        fig, ax = plt.subplots(figsize=(10, 7))
        sc = ax.scatter(
            df_margen["ingresos_netos"] / 1_000_000,
            df_margen["margen_pct"],
            s=df_margen["unidades_vendidas"] / df_margen["unidades_vendidas"].max() * 400 + 20,
            alpha=0.7,
            c=df_margen["margen_pct"],
            cmap="RdYlGn",
        )
        ax.axhline(y=df_margen["margen_pct"].median(), color="gray", linestyle="--", alpha=0.5, label="Mediana margen")
        ax.set_xlabel("Ingresos Netos (millones CLP)")
        ax.set_ylabel("Margen Bruto %")
        ax.set_title("Margen vs Ingresos — Top 50 productos\n(tamaño = volumen unidades)")
        plt.colorbar(sc, ax=ax, label="Margen %")
        ax.legend()
        plt.tight_layout()
        ruta2 = output_dir / f"scatter_margen_ingresos_{hoy}.png"
        fig.savefig(ruta2, dpi=150)
        plt.close(fig)
        logger.info("Gráfico guardado: %s", ruta2)


# ---------------------------------------------------------------------------
# Exportación CSV
# ---------------------------------------------------------------------------

def exportar_csv(df_top: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    hoy = date.today().strftime("%Y%m%d")
    ruta = output_dir / f"top_productos_{hoy}.csv"
    df_top.to_csv(ruta, index_label="rank", float_format="%.2f", encoding="utf-8-sig")
    logger.info("CSV exportado: %s (%d filas)", ruta, len(df_top))
    return ruta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fecha_desde(meses: int) -> str:
    import calendar as cal
    hoy = date.today()
    anio = hoy.year - (meses // 12)
    mes = hoy.month - (meses % 12)
    if mes <= 0:
        mes += 12
        anio -= 1
    dia = min(hoy.day, cal.monthrange(anio, mes)[1])
    return date(anio, mes, dia).strftime("%Y-%m-%d")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Análisis top productos por ingresos desde Supabase."
    )
    parser.add_argument("--top", type=int, default=TOP_DEFAULT, help=f"Cantidad de productos (default {TOP_DEFAULT})")
    parser.add_argument("--meses", type=int, default=MESES_DEFAULT, help=f"Meses hacia atrás (default {MESES_DEFAULT})")
    parser.add_argument("--desde", metavar="YYYY-MM-DD", help="Fecha inicio (sobreescribe --meses)")
    parser.add_argument("--sin-graficos", action="store_true", help="No generar imágenes")
    args = parser.parse_args()

    desde = args.desde or _fecha_desde(args.meses)
    logger.info("Período de análisis: %s → hoy", desde)

    supabase = _supabase()
    df_detalle = cargar_detalle_ventas(supabase, desde)

    if df_detalle.empty:
        logger.error("Sin datos para analizar. Verificar que la carga histórica esté completa.")
        sys.exit(1)

    df_costos = cargar_costos_productos(supabase)
    df_top = calcular_top_productos(df_detalle, df_costos, top_n=args.top)

    # Imprime resumen en consola
    resumen = resumen_ejecutivo(df_top, df_detalle)
    print("\n" + "=" * 60)
    print(f"  ANÁLISIS TOP {args.top} PRODUCTOS — El Chillanejo")
    print(f"  Período: {resumen.get('fecha_min')} → {resumen.get('fecha_max')}")
    print("=" * 60)
    print(f"  Ingresos totales netos : ${resumen.get('total_ingresos_netos', 0):,.0f} CLP")
    print(f"  Ingresos top productos : ${resumen.get('ingresos_top_productos', 0):,.0f} CLP")
    print(f"  Concentración          : {resumen.get('concentracion_pct', 0):.1f}% del total")
    print(f"  Productos distintos    : {resumen.get('productos_distintos', 0)}")
    print("=" * 60)

    cols_display = [
        "codigo_producto", "nombre_producto",
        "unidades_vendidas", "ingresos_netos",
        "margen_pct", "rank_ingresos",
    ]
    pd.set_option("display.max_colwidth", 35)
    pd.set_option("display.float_format", "{:,.0f}".format)
    print(df_top[cols_display].head(20).to_string())

    # Exportaciones
    exportar_csv(df_top, OUTPUT_DIR)
    if not args.sin_graficos:
        generar_graficos(df_top, OUTPUT_DIR)
