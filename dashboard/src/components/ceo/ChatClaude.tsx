import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { supabase } from "@/lib/supabase";

interface Mensaje {
  rol: "user" | "assistant";
  contenido: string;
  timestamp: Date;
}

interface Props {
  contextoNegocio?: string;
}

export function ChatClaude({ contextoNegocio }: Props) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([
    {
      rol: "assistant",
      contenido:
        "Hola Daniel. Tengo acceso a los datos de El Chillanejo. " +
        "Puedo analizar ventas, márgenes, stock, proyecciones o cualquier aspecto del negocio. " +
        "¿En qué te ayudo hoy?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [enviando, setEnviando] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  const enviar = async () => {
    const texto = input.trim();
    if (!texto || enviando) return;

    const mensajeUsuario: Mensaje = { rol: "user", contenido: texto, timestamp: new Date() };
    setMensajes((prev) => [...prev, mensajeUsuario]);
    setInput("");
    setEnviando(true);

    try {
      // Llama al Edge Function de Supabase que hace proxy a Claude API
      const { data, error } = await supabase.functions.invoke("chat-ceo", {
        body: {
          mensaje: texto,
          historial: mensajes.slice(-8).map((m) => ({
            role: m.rol,
            content: m.contenido,
          })),
          contexto: contextoNegocio,
        },
      });

      if (error) throw error;

      setMensajes((prev) => [
        ...prev,
        {
          rol: "assistant",
          contenido: data.respuesta ?? "Sin respuesta del asistente.",
          timestamp: new Date(),
        },
      ]);
    } catch (e: unknown) {
      setMensajes((prev) => [
        ...prev,
        {
          rol: "assistant",
          contenido: "Error al conectar con el asistente. Intenta de nuevo.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setEnviando(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <div className="flex flex-col h-[520px] rounded-xl border bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <div className="rounded-full bg-blue-50 p-1.5">
          <Bot className="h-4 w-4 text-blue-600" />
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-800">Asistente de negocio</p>
          <p className="text-xs text-gray-400">Claude · Solo disponible para Daniel</p>
        </div>
      </div>

      {/* Mensajes */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {mensajes.map((m, i) => (
          <div
            key={i}
            className={`flex gap-2.5 ${m.rol === "user" ? "justify-end" : "justify-start"}`}
          >
            {m.rol === "assistant" && (
              <div className="shrink-0 rounded-full bg-blue-50 p-1.5 h-fit mt-0.5">
                <Bot className="h-3.5 w-3.5 text-blue-600" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                m.rol === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-50 text-gray-800 rounded-bl-sm border"
              }`}
            >
              {m.contenido}
            </div>
            {m.rol === "user" && (
              <div className="shrink-0 rounded-full bg-gray-100 p-1.5 h-fit mt-0.5">
                <User className="h-3.5 w-3.5 text-gray-500" />
              </div>
            )}
          </div>
        ))}
        {enviando && (
          <div className="flex gap-2.5 items-center">
            <div className="shrink-0 rounded-full bg-blue-50 p-1.5">
              <Bot className="h-3.5 w-3.5 text-blue-600" />
            </div>
            <div className="bg-gray-50 border rounded-2xl rounded-bl-sm px-3.5 py-2.5">
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t px-3 py-3">
        <div className="flex items-end gap-2 rounded-xl border bg-gray-50 px-3 py-2 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-400/20 transition-all">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Pregunta sobre ventas, márgenes, stock..."
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-gray-800 placeholder-gray-400 focus:outline-none max-h-32"
          />
          <button
            onClick={enviar}
            disabled={!input.trim() || enviando}
            className="shrink-0 rounded-lg bg-blue-600 p-1.5 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
        <p className="mt-1.5 text-center text-xs text-gray-300">Enter para enviar · Shift+Enter nueva línea</p>
      </div>
    </div>
  );
}
