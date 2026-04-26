import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { RutaProtegida } from "@/components/RutaProtegida";
import Login from "@/pages/Login";
import DashboardOperativo from "@/pages/DashboardOperativo";
import DashboardEjecutivo from "@/pages/DashboardEjecutivo";
import DashboardCeo from "@/pages/DashboardCeo";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route
            path="/operativo"
            element={
              <RutaProtegida rolesPermitidos={["owner", "socio", "operativo"]}>
                <DashboardOperativo />
              </RutaProtegida>
            }
          />

          <Route
            path="/ejecutivo"
            element={
              <RutaProtegida rolesPermitidos={["owner", "socio"]}>
                <DashboardEjecutivo />
              </RutaProtegida>
            }
          />

          <Route
            path="/ceo"
            element={
              <RutaProtegida rolesPermitidos={["owner"]}>
                <DashboardCeo />
              </RutaProtegida>
            }
          />

          <Route path="/" element={<Navigate to="/operativo" replace />} />

          <Route
            path="*"
            element={
              <div className="min-h-screen flex items-center justify-center text-gray-400">
                Página no encontrada
              </div>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
