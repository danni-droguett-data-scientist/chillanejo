import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { clp, pct } from "@/lib/formato";

interface Props {
  titulo: string;
  valor: number | null;
  formato?: "clp" | "numero";
  variacionPct?: number | null;
  subtitulo?: string;
  icono?: React.ReactNode;
  cargando?: boolean;
}

export function TarjetaKpi({
  titulo,
  valor,
  formato = "clp",
  variacionPct,
  subtitulo,
  icono,
  cargando = false,
}: Props) {
  const valorFormateado =
    valor == null ? "—" : formato === "clp" ? clp(valor) : String(valor);

  const signo =
    variacionPct == null
      ? null
      : variacionPct > 0
      ? "sube"
      : variacionPct < 0
      ? "baja"
      : "igual";

  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm flex flex-col gap-3">
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span className="font-medium">{titulo}</span>
        {icono && <span className="text-gray-400">{icono}</span>}
      </div>

      {cargando ? (
        <div className="h-8 w-32 animate-pulse rounded bg-gray-100" />
      ) : (
        <p className="text-2xl font-bold text-gray-900 tabular-nums">
          {valorFormateado}
        </p>
      )}

      {(variacionPct != null || subtitulo) && (
        <div className="flex items-center gap-1.5 text-xs">
          {variacionPct != null && (
            <span
              className={`flex items-center gap-0.5 font-semibold ${
                signo === "sube"
                  ? "text-emerald-600"
                  : signo === "baja"
                  ? "text-red-500"
                  : "text-gray-400"
              }`}
            >
              {signo === "sube" && <ArrowUpRight className="h-3.5 w-3.5" />}
              {signo === "baja" && <ArrowDownRight className="h-3.5 w-3.5" />}
              {signo === "igual" && <Minus className="h-3.5 w-3.5" />}
              {pct(Math.abs(variacionPct))}
            </span>
          )}
          {subtitulo && <span className="text-gray-400">{subtitulo}</span>}
        </div>
      )}
    </div>
  );
}
