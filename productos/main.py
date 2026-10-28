"""
Microservicio de PRODUCTOS
Responsabilidad: administrar el catálogo de la tienda virtual.
Puerto: 8001
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Microservicio de Productos", version="1.0")
# Permite que la interfaz web (interfaz/index.html) consuma la API desde el navegador
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ProductoEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    precio: float = Field(gt=0)
    stock: int = Field(ge=0)


class Producto(ProductoEntrada):
    id: int


# Almacenamiento en memoria (en un sistema real: base de datos propia del servicio)
productos: list[Producto] = [
    Producto(id=1, nombre="Teclado mecánico", precio=180000, stock=15),
    Producto(id=2, nombre="Mouse inalámbrico", precio=75000, stock=40),
    Producto(id=3, nombre="Monitor 24 pulgadas", precio=650000, stock=8),
]


@app.get("/salud")
def salud():
    return {"servicio": "productos", "estado": "activo"}


@app.get("/productos", response_model=list[Producto])
def listar_productos():
    return productos


@app.get("/productos/{producto_id}", response_model=Producto)
def obtener_producto(producto_id: int):
    for p in productos:
        if p.id == producto_id:
            return p
    raise HTTPException(status_code=404, detail="Producto no encontrado")


@app.post("/productos", response_model=Producto, status_code=201)
def registrar_producto(datos: ProductoEntrada):
    nuevo_id = max((p.id for p in productos), default=0) + 1
    producto = Producto(id=nuevo_id, **datos.model_dump())
    productos.append(producto)
    return producto


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
