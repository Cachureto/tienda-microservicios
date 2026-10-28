"""
Microservicio de CLIENTES
Responsabilidad: registrar y consultar los clientes de la tienda.
Puerto: 8002
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Microservicio de Clientes", version="1.0")
# Permite que la interfaz web (interfaz/index.html) consuma la API desde el navegador
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ClienteEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    correo: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    ciudad: str = "Bogotá"


class Cliente(ClienteEntrada):
    id: int


clientes: list[Cliente] = [
    Cliente(id=1, nombre="Ana Gómez", correo="ana@correo.com", ciudad="Bogotá"),
    Cliente(id=2, nombre="Luis Pérez", correo="luis@correo.com", ciudad="Medellín"),
]


@app.get("/salud")
def salud():
    return {"servicio": "clientes", "estado": "activo"}


@app.get("/clientes", response_model=list[Cliente])
def listar_clientes():
    return clientes


@app.get("/clientes/{cliente_id}", response_model=Cliente)
def obtener_cliente(cliente_id: int):
    for c in clientes:
        if c.id == cliente_id:
            return c
    raise HTTPException(status_code=404, detail="Cliente no encontrado")


@app.post("/clientes", response_model=Cliente, status_code=201)
def registrar_cliente(datos: ClienteEntrada):
    if any(c.correo == datos.correo for c in clientes):
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese correo")
    nuevo_id = max((c.id for c in clientes), default=0) + 1
    cliente = Cliente(id=nuevo_id, **datos.model_dump())
    clientes.append(cliente)
    return cliente


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
