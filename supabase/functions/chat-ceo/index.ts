import Anthropic from "npm:@anthropic-ai/sdk@0.30.1";

const SYSTEM_PROMPT = `Eres el asistente de negocio personal de Daniel Droguett, CEO y Data Scientist de El Chillanejo.
El Chillanejo es una distribuidora de aseo y abarrotes en Chillán, Chile.

Tu rol:
- Analizar datos del negocio y responder preguntas sobre ventas, márgenes, stock y tendencias.
- Hablar en español, tono directo y profesional, sin rodeos.
- Usar números en formato chileno (puntos para miles, coma para decimales).
- Cuando no tengas datos suficientes para responder con certeza, decirlo explícitamente.
- Dar recomendaciones accionables cuando sea pertinente.

No reveles información confidencial de terceros. No generes datos ficticios.`;

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "authorization, content-type",
      },
    });
  }

  try {
    const { mensaje, historial = [], contexto } = await req.json();

    const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
    if (!apiKey) throw new Error("ANTHROPIC_API_KEY no configurada en secrets.");

    const client = new Anthropic({ apiKey });

    const systemConContexto = contexto
      ? `${SYSTEM_PROMPT}\n\nContexto actual del negocio:\n${contexto}`
      : SYSTEM_PROMPT;

    const messages: { role: "user" | "assistant"; content: string }[] = [
      ...historial,
      { role: "user", content: mensaje },
    ];

    const response = await client.messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 1024,
      system: systemConContexto,
      messages,
    });

    const respuesta =
      response.content[0].type === "text" ? response.content[0].text : "";

    return new Response(JSON.stringify({ respuesta }), {
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (error: unknown) {
    const mensaje = error instanceof Error ? error.message : "Error desconocido";
    return new Response(JSON.stringify({ error: mensaje }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
