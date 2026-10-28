"""
Microservicio de PEDIDOS
Responsabilidad: registrar pedidos y consultar su estado.
Puerto: 8003

Depende de Productos (8001) y Clientes (8002), pero NO se cae si alguno de
ellos deja de responder. Mecanismos de tolerancia a fallos:
  1. Tiempo límite (timeout) en cada llamada HTTP.
  2. Reintentos automáticos.
  3. Cortocircuito (circuit breaker): tras varios fallos seguidos deja de
     llamar al servicio caído por unos segundos y responde de inmediato.
  4. Caché local con la última información conocida de productos y clientes.
  5. Degradación controlada: si no hay datos, el pedido queda
     PENDIENTE_VALIDACION y se puede revalidar cuando el servicio vuelva.
"""
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

URL_PRODUCTOS = os.getenv("URL_PRODUCTOS", "http://127.0.0.1:8001")
URL_CLIENTES = os.getenv("URL_CLIENTES", "http://127.0.0.1:8002")
TIMEOUT_SEGUNDOS = 2.0
REINTENTOS = 2
FALLOS_PARA_ABRIR = 3
SEGUNDOS_CIRCUITO_ABIERTO = 15


# ---------------------------------------------------------------------------
# Cortocircuito (circuit breaker)
# ---------------------------------------------------------------------------
class Cortocircuito:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.fallos = 0
        self.abierto_hasta = 0.0

    def permite_llamada(self) -> bool:
        return time.time() >= self.abierto_hasta

    def registrar_exito(self):
        self.fallos = 0
        self.abierto_hasta = 0.0

    def registrar_fallo(self):
        self.fallos += 1
        if self.fallos >= FALLOS_PARA_ABRIR:
            self.abierto_hasta = time.time() + SEGUNDOS_CIRCUITO_ABIERTO

    @property
    def estado(self) -> str:
        return "ABIERTO" if not self.permite_llamada() else "CERRADO"


circuitos = {"productos": Cortocircuito("productos"), "clientes": Cortocircuito("clientes")}
cache_productos: dict[int, dict] = {}
cache_clientes: dict[int, dict] = {}


def consultar(servicio: str, url: str):
    """Devuelve (datos, resultado) con resultado en: ok | no_encontrado | no_disponible."""
    circuito = circuitos[servicio]
    if not circuito.permite_llamada():
        return None, "no_disponible"
    for _ in range(REINTENTOS):
        try:
            r = httpx.get(url, timeout=TIMEOUT_SEGUNDOS)
            circuito.registrar_exito()
            if r.status_code == 404:
                return None, "no_encontrado"
            r.raise_for_status()
            return r.json(), "ok"
        except (httpx.RequestError, httpx.HTTPStatusError):
            continue
    circuito.registrar_fallo()
    return None, "no_disponible"


def precargar_cache():
    """Intenta llenar la caché al arrancar; si un servicio no está, no pasa nada."""
    datos, res = consultar("productos", f"{URL_PRODUCTOS}/productos")
    if res == "ok":
        cache_productos.update({p["id"]: p for p in datos})
    datos, res = consultar("clientes", f"{URL_CLIENTES}/clientes")
    if res == "ok":
        cache_clientes.update({c["id"]: c for c in datos})


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    precargar_cache()
    yield


app = FastAPI(title="Microservicio de Pedidos", version="1.0", lifespan=ciclo_de_vida)
# Permite que la interfaz web (interfaz/index.html) consuma la API desde el navegador
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class ItemPedido(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0)


class PedidoEntrada(BaseModel):
    cliente_id: int
    items: list[ItemPedido] = Field(min_length=1)


pedidos: list[dict] = []


# ---------------------------------------------------------------------------
# Lógica de validación
# ---------------------------------------------------------------------------
def validar_cliente(cliente_id: int):
    datos, res = consultar("clientes", f"{URL_CLIENTES}/clientes/{cliente_id}")
    if res == "ok":
        cache_clientes[cliente_id] = datos
        return datos, "en_linea"
    if res == "no_encontrado":
        raise HTTPException(status_code=404, detail=f"Cliente {cliente_id} no existe")
    if cliente_id in cache_clientes:
        return cache_clientes[cliente_id], "cache"
    return None, "sin_datos"


def validar_producto(item: ItemPedido):
    datos, res = consultar("productos", f"{URL_PRODUCTOS}/productos/{item.producto_id}")
    if res == "ok":
        cache_productos[item.producto_id] = datos
        if datos["stock"] < item.cantidad:
            raise HTTPException(
                status_code=409,
                detail=f"Stock insuficiente para '{datos['nombre']}' (disponible: {datos['stock']})",
            )
        return datos, "en_linea"
    if res == "no_encontrado":
        raise HTTPException(status_code=404, detail=f"Producto {item.producto_id} no existe")
    if item.producto_id in cache_productos:
        return cache_productos[item.producto_id], "cache"
    return None, "sin_datos"


def construir_pedido(entrada: PedidoEntrada) -> dict:
    cliente, origen_cliente = validar_cliente(entrada.cliente_id)
    origenes = [origen_cliente]
    detalle, total = [], 0.0
    for item in entrada.items:
        prod, origen = validar_producto(item)
        origenes.append(origen)
        if prod:
            subtotal = prod["precio"] * item.cantidad
            total += subtotal
            detalle.append({"producto_id": item.producto_id, "nombre": prod["nombre"],
                            "cantidad": item.cantidad, "precio_unitario": prod["precio"],
                            "subtotal": subtotal})
        else:
            detalle.append({"producto_id": item.producto_id, "nombre": None,
                            "cantidad": item.cantidad, "precio_unitario": None, "subtotal": None})

    if "sin_datos" in origenes:
        estado, total = "PENDIENTE_VALIDACION", None
    elif "cache" in origenes:
        estado = "CONFIRMADO_CON_CACHE"
    else:
        estado = "CONFIRMADO"

    return {"cliente_id": entrada.cliente_id,
            "cliente": cliente["nombre"] if cliente else None,
            "items": detalle, "total": total, "estado": estado}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/salud")
def salud():
    _, res_p = consultar("productos", f"{URL_PRODUCTOS}/salud")
    _, res_c = consultar("clientes", f"{URL_CLIENTES}/salud")
    return {
        "servicio": "pedidos",
        "estado": "activo",
        "dependencias": {
            "productos": {"disponible": res_p == "ok", "circuito": circuitos["productos"].estado},
            "clientes": {"disponible": res_c == "ok", "circuito": circuitos["clientes"].estado},
        },
        "cache": {"productos": len(cache_productos), "clientes": len(cache_clientes)},
    }


@app.post("/pedidos", status_code=201)
def registrar_pedido(entrada: PedidoEntrada):
    pedido = construir_pedido(entrada)
    pedido["id"] = len(pedidos) + 1
    pedido["fecha"] = datetime.now().isoformat(timespec="seconds")
    pedido["solicitud"] = entrada.model_dump()
    pedidos.append(pedido)
    return pedido


@app.get("/pedidos")
def listar_pedidos():
    return pedidos


@app.get("/pedidos/{pedido_id}")
def obtener_pedido(pedido_id: int):
    for p in pedidos:
        if p["id"] == pedido_id:
            return p
    raise HTTPException(status_code=404, detail="Pedido no encontrado")


@app.get("/pedidos/{pedido_id}/estado")
def estado_pedido(pedido_id: int):
    p = obtener_pedido(pedido_id)
    return {"id": p["id"], "estado": p["estado"]}


@app.post("/pedidos/revalidar")
def revalidar_pendientes():
    """Vuelve a validar los pedidos pendientes cuando los servicios se recuperan."""
    actualizados = []
    for p in pedidos:
        if p["estado"] in ("PENDIENTE_VALIDACION", "CONFIRMADO_CON_CACHE"):
            try:
                nuevo = construir_pedido(PedidoEntrada(**p["solicitud"]))
            except HTTPException as e:
                p["estado"], p["observacion"] = "RECHAZADO", e.detail
                actualizados.append({"id": p["id"], "estado": p["estado"]})
                continue
            if nuevo["estado"] != p["estado"]:
                p.update(nuevo)
                actualizados.append({"id": p["id"], "estado": p["estado"]})
    return {"revisados": len(pedidos), "actualizados": actualizados}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
