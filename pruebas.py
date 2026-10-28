"""
Pruebas de la tienda virtual con microservicios.
Levanta los tres servicios, prueba sus API y simula la caída de cada
servicio para demostrar que los demás siguen funcionando.

Uso:  python pruebas.py
"""
import json
import os
import subprocess
import sys
import time

import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
SERVICIOS = {
    "productos": ("productos/main.py", 8001),
    "clientes": ("clientes/main.py", 8002),
    "pedidos": ("pedidos/main.py", 8003),
}
procesos: dict[str, subprocess.Popen] = {}
resultados: list[tuple[str, bool]] = []


def iniciar(nombre):
    ruta, puerto = SERVICIOS[nombre]
    procesos[nombre] = subprocess.Popen(
        [sys.executable, os.path.join(BASE, ruta)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{puerto}/salud", timeout=0.5)
            return
        except httpx.RequestError:
            time.sleep(0.2)
    raise RuntimeError(f"No arrancó el servicio {nombre}")


def detener(nombre):
    procesos[nombre].terminate()
    procesos[nombre].wait()


def llamar(metodo, puerto, ruta, cuerpo=None):
    try:
        r = httpx.request(metodo, f"http://127.0.0.1:{puerto}{ruta}", json=cuerpo, timeout=10)
        return r.status_code, r.json()
    except httpx.RequestError:
        return None, "SIN CONEXIÓN"


def prueba(descripcion, metodo, puerto, ruta, cuerpo=None, esperado=None, mostrar=True):
    codigo, datos = llamar(metodo, puerto, ruta, cuerpo)
    ok = esperado(codigo, datos) if esperado else codigo is not None and codigo < 400
    resultados.append((descripcion, ok))
    print(f"\n[{'OK ' if ok else 'FALLA'}] {descripcion}")
    print(f"      {metodo} :{puerto}{ruta} -> {codigo if codigo else 'sin respuesta'}")
    if mostrar:
        texto = json.dumps(datos, ensure_ascii=False, indent=2)
        lineas = texto.splitlines()
        for linea in lineas[:14]:
            print("      " + linea)
        if len(lineas) > 14:
            print("      ...")
    return codigo, datos


def titulo(texto):
    print("\n" + "=" * 70 + f"\n  {texto}\n" + "=" * 70)


def main():
    try:
        titulo("FASE 1: Todos los servicios activos")
        for n in SERVICIOS:
            iniciar(n)
        prueba("Consultar catálogo", "GET", 8001, "/productos", mostrar=False)
        prueba("Registrar producto", "POST", 8001, "/productos",
               {"nombre": "Audífonos Bluetooth", "precio": 120000, "stock": 25},
               esperado=lambda c, d: c == 201)
        prueba("Registrar cliente", "POST", 8002, "/clientes",
               {"nombre": "María Rodríguez", "correo": "maria@correo.com", "ciudad": "Cali"},
               esperado=lambda c, d: c == 201)
        prueba("Consultar cliente 3", "GET", 8002, "/clientes/3")
        prueba("Registrar pedido (todo en línea)", "POST", 8003, "/pedidos",
               {"cliente_id": 3, "items": [{"producto_id": 1, "cantidad": 1},
                                           {"producto_id": 4, "cantidad": 2}]},
               esperado=lambda c, d: c == 201 and d["estado"] == "CONFIRMADO")
        prueba("Rechazar pedido con producto inexistente", "POST", 8003, "/pedidos",
               {"cliente_id": 1, "items": [{"producto_id": 99, "cantidad": 1}]},
               esperado=lambda c, d: c == 404)
        prueba("Rechazar pedido sin stock suficiente", "POST", 8003, "/pedidos",
               {"cliente_id": 1, "items": [{"producto_id": 3, "cantidad": 100}]},
               esperado=lambda c, d: c == 409)

        titulo("FASE 2: Se cae el servicio de PRODUCTOS")
        detener("productos")
        prueba("Productos ya no responde", "GET", 8001, "/productos",
               esperado=lambda c, d: c is None, mostrar=False)
        prueba("Clientes sigue funcionando", "GET", 8002, "/clientes", mostrar=False)
        prueba("Salud de pedidos reporta la caída", "GET", 8003, "/salud",
               esperado=lambda c, d: c == 200 and not d["dependencias"]["productos"]["disponible"])
        prueba("Pedido con producto en caché -> CONFIRMADO_CON_CACHE", "POST", 8003, "/pedidos",
               {"cliente_id": 1, "items": [{"producto_id": 2, "cantidad": 1}]},
               esperado=lambda c, d: c == 201 and d["estado"] == "CONFIRMADO_CON_CACHE")
        prueba("Pedidos sigue listando y consultando estados", "GET", 8003, "/pedidos/1/estado")

        titulo("FASE 3: Productos sigue caído, pedido pendiente y recuperación")
        prueba("Pedido con producto que Pedidos no conoce -> PENDIENTE_VALIDACION", "POST", 8003,
               "/pedidos", {"cliente_id": 2, "items": [{"producto_id": 5, "cantidad": 1}]},
               esperado=lambda c, d: c == 201 and d["estado"] == "PENDIENTE_VALIDACION")
        prueba("Cortocircuito ABIERTO tras fallos repetidos", "GET", 8003, "/salud",
               esperado=lambda c, d: d["dependencias"]["productos"]["circuito"] == "ABIERTO")
        iniciar("productos")
        print("\n      (Productos reiniciado: su lista en memoria vuelve al estado inicial)")
        prueba("Re-registrar producto 4", "POST", 8001, "/productos",
               {"nombre": "Audífonos Bluetooth", "precio": 120000, "stock": 25},
               esperado=lambda c, d: c == 201, mostrar=False)
        prueba("Registrar producto 5", "POST", 8001, "/productos",
               {"nombre": "Escritorio en L", "precio": 540000, "stock": 3},
               esperado=lambda c, d: c == 201)
        print("\n      (esperando 15 s a que el cortocircuito se cierre...)")
        time.sleep(16)
        prueba("Revalidar pedidos pendientes", "POST", 8003, "/pedidos/revalidar",
               esperado=lambda c, d: c == 200 and all(a["estado"] == "CONFIRMADO" for a in d["actualizados"]))
        prueba("Consultar estado del pedido 3", "GET", 8003, "/pedidos/3/estado",
               esperado=lambda c, d: d["estado"] == "CONFIRMADO")

        titulo("FASE 4: Se cae el servicio de CLIENTES")
        detener("clientes")
        prueba("Productos sigue funcionando", "GET", 8001, "/productos/1")
        prueba("Pedido de cliente en caché sigue registrándose", "POST", 8003, "/pedidos",
               {"cliente_id": 1, "items": [{"producto_id": 1, "cantidad": 1}]},
               esperado=lambda c, d: c == 201 and d["estado"] == "CONFIRMADO_CON_CACHE")
        iniciar("clientes")

        titulo("FASE 5: Se cae el servicio de PEDIDOS")
        detener("pedidos")
        prueba("Pedidos no responde", "GET", 8003, "/pedidos",
               esperado=lambda c, d: c is None, mostrar=False)
        prueba("Productos sigue funcionando", "GET", 8001, "/productos", mostrar=False)
        prueba("Clientes sigue funcionando", "GET", 8002, "/clientes", mostrar=False)

        titulo("RESUMEN")
        aprobadas = sum(ok for _, ok in resultados)
        for desc, ok in resultados:
            print(f"  [{'OK ' if ok else 'FALLA'}] {desc}")
        print(f"\n  {aprobadas}/{len(resultados)} pruebas aprobadas")
    finally:
        for p in procesos.values():
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
