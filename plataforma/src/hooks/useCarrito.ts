import { useState, useEffect } from "react";
import { carrito } from "@/store/carrito";
import type { ItemCarrito } from "@/store/carrito";

export function useCarrito() {
  const [items, setItems] = useState<ItemCarrito[]>(carrito.getEstado().items);

  useEffect(() => {
    return carrito.subscribe(() => {
      setItems([...carrito.getEstado().items]);
    });
  }, []);

  return {
    items,
    totales: carrito.totales(),
    agregar: carrito.agregar,
    cambiarCantidad: carrito.cambiarCantidad,
    quitar: carrito.quitar,
    vaciar: carrito.vaciar,
  };
}
