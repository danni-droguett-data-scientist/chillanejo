import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ItemCarrito {
  relbase_id: number;
  sku: string;
  nombre: string;
  precio_neto: number;
  precio_bruto: number;
  cantidad: number;
  imagen_url?: string;
}

interface CarritoStore {
  items: ItemCarrito[];
  agregar:         (producto: Omit<ItemCarrito, "cantidad">, cantidad?: number) => void;
  cambiarCantidad: (relbase_id: number, cantidad: number) => void;
  quitar:          (relbase_id: number) => void;
  vaciar:          () => void;
}

export const useCarritoStore = create<CarritoStore>()(
  persist(
    (set) => ({
      items: [],

      agregar: (producto, cantidad = 1) =>
        set((state) => {
          const existente = state.items.find(
            (i) => i.relbase_id === producto.relbase_id
          );
          if (existente) {
            return {
              items: state.items.map((i) =>
                i.relbase_id === producto.relbase_id
                  ? { ...i, cantidad: i.cantidad + cantidad }
                  : i
              ),
            };
          }
          return { items: [...state.items, { ...producto, cantidad }] };
        }),

      cambiarCantidad: (relbase_id, cantidad) =>
        set((state) => {
          if (cantidad <= 0) {
            return { items: state.items.filter((i) => i.relbase_id !== relbase_id) };
          }
          return {
            items: state.items.map((i) =>
              i.relbase_id === relbase_id ? { ...i, cantidad } : i
            ),
          };
        }),

      quitar: (relbase_id) =>
        set((state) => ({
          items: state.items.filter((i) => i.relbase_id !== relbase_id),
        })),

      vaciar: () => set({ items: [] }),
    }),
    { name: "carrito-elchillanejo" }
  )
);
