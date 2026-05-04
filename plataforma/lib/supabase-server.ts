import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

// Cliente Supabase para Server Components y Route Handlers.
// Solo lectura de cookies — no escribe ni refresca la sesión.
export function createSupabaseServer() {
  const cookieStore = cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get: (name: string) => cookieStore.get(name)?.value,
        set:    (_name: string, _value: string, _opts: CookieOptions) => {},
        remove: (_name: string, _opts: CookieOptions)                 => {},
      },
    }
  );
}
