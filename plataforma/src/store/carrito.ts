/**
 * carrito.ts — Estado global del carrito usando vanilla store (sin Redux).
 * API simple: getCarrito(), agregarItem(), quitarItem(), vaciar(), subscribe().
 */

export interface ItemCarrito {
  producto_id_relbase: number;
  codigo: string;
  nombre: string;
  precio_neto: number;
  precio_bruto: number;
  cantidad: number;
  imagen_url?: string;
}

type Listener = () => void;

interface EstadoCarrito {
  items: ItemCarrito[];
}

let estado: EstadoCarrito = { items: [] };
const listeners = new Set<Listener>();

function notificar() {
  listeners.forEach((fn) => fn());
}

export const carrito = {
  getEstado: (): EstadoCarrito => estado,

  subscribe: (fn: Listener): (() => void) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  agregar: (producto: Omit<ItemCarrito, "cantidad">, cantidad = 1) => {
    const existente = estado.items.find(
      (i) => i.producto_id_relbase === producto.producto_id_relbase
    );
    if (existente) {
      estado = {
        items: estado.items.map((i) =>
          i.producto_id_relbase === producto.producto_id_relbase
            ? { ...i, cantidad: i.cantidad + cantidad }
            : i
        ),
      };
    } else {
      estado = { items: [...estado.items, { ...producto, cantidad }] };
    }
    notificar();
  },

  cambiarCantidad: (producto_id_relbase: number, cantidad: number) => {
    if (cantidad <= 0) {
      carrito.quitar(producto_id_relbase);
      return;
    }
    estado = {
      items: estado.items.map((i) =>
        i.producto_id_relbase === producto_id_relbase ? { ...i, cantidad } : i
      ),
    };
    notificar();
  },

  quitar: (producto_id_relbase: number) => {
    estado = {
      items: estado.items.filter((i) => i.producto_id_relbase !== producto_id_relbase),
    };
    notificar();
  },

  vaciar: () => {
    estado = { items: [] };
    notificar();
  },

  totales: () => {
    const items = estado.items;
    const subtotal_neto  = items.reduce((s, i) => s + i.precio_neto  * i.cantidad, 0);
    const subtotal_bruto = items.reduce((s, i) => s + i.precio_bruto * i.cantidad, 0);
    const iva            = subtotal_bruto - subtotal_neto;
    const num_items      = items.reduce((s, i) => s + i.cantidad, 0);
    return { subtotal_neto, subtotal_bruto, iva, num_items };
  },
};
