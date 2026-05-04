import { useCarritoStore } from "@/store/carrito";

export function useCarrito() {
  const items           = useCarritoStore((s) => s.items);
  const agregar         = useCarritoStore((s) => s.agregar);
  const cambiarCantidad = useCarritoStore((s) => s.cambiarCantidad);
  const quitar          = useCarritoStore((s) => s.quitar);
  const vaciar          = useCarritoStore((s) => s.vaciar);

  const subtotal_neto  = items.reduce((s, i) => s + i.precio_neto  * i.cantidad, 0);
  const subtotal_bruto = items.reduce((s, i) => s + i.precio_bruto * i.cantidad, 0);
  const totales = {
    subtotal_neto,
    subtotal_bruto,
    iva:       subtotal_bruto - subtotal_neto,
    num_items: items.reduce((s, i) => s + i.cantidad, 0),
  };

  return { items, agregar, cambiarCantidad, quitar, vaciar, totales };
}
