import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "El Chillanejo — Distribuidora",
  description: "Distribuidora de aseo y abarrotes en Chillán. Compra online con retiro en local.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-white text-gray-900 antialiased">{children}</body>
    </html>
  );
}
