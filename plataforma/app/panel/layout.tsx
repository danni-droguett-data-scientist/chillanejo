import { redirect } from "next/navigation";
import { createSupabaseServer } from "@/lib/supabase-server";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const supabase = createSupabaseServer();
  const { data: { session } } = await supabase.auth.getSession();

  const rol = session?.user?.user_metadata?.app_role as string | undefined;
  if (!session || rol !== "mirella") {
    redirect("/");
  }

  return <>{children}</>;
}
