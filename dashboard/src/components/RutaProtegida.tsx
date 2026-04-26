import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

interface Props {
  children: React.ReactNode;
  rolesPermitidos?: string[];
}

export function RutaProtegida({ children, rolesPermitidos }: Props) {
  const { session, rolApp, cargando } = useAuth();

  if (cargando) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!session) return <Navigate to="/login" replace />;

  if (rolesPermitidos && rolApp && !rolesPermitidos.includes(rolApp)) {
    return (
      <div className="min-h-screen flex items-center justify-center text-center px-4">
        <div>
          <p className="text-lg font-semibold text-gray-800">Sin acceso</p>
          <p className="text-sm text-gray-500 mt-1">
            Tu rol no tiene permiso para ver esta página.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
