# Tienda virtual con microservicios (FastAPI)

Tres servicios independientes que se comunican por API REST:

| Servicio  | Puerto | Endpoints principales |
|-----------|--------|-----------------------|
| Productos | 8001   | `GET /productos`, `GET /productos/{id}`, `POST /productos`, `GET /salud` |
| Clientes  | 8002   | `GET /clientes`, `GET /clientes/{id}`, `POST /clientes`, `GET /salud` |
| Pedidos   | 8003   | `POST /pedidos`, `GET /pedidos`, `GET /pedidos/{id}`, `GET /pedidos/{id}/estado`, `POST /pedidos/revalidar`, `GET /salud` |

## Instalación

```bash
python -m venv venv
# Windows: venv\Scripts\activate    Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

Opción A, todos juntos: `python iniciar_servicios.py`

Opción B, cada uno en su terminal (permite apagar uno con Ctrl+C para demostrar la tolerancia a fallos):

```bash
python productos/main.py
python clientes/main.py
python pedidos/main.py
```

La documentación técnica (Swagger) sigue disponible en `http://127.0.0.1:800X/docs`.

## Interfaz web

`python iniciar_servicios.py` abre automáticamente `interfaz/index.html` en el navegador. También se puede abrir con doble clic con los servicios encendidos.

La interfaz muestra arriba el estado de cada servicio (se revisa cada 3 segundos). Si uno se cae, su columna se marca en rojo y las demás siguen funcionando.

## Pruebas automáticas

```bash
python pruebas.py
```

Levanta los servicios, prueba todas las API y apaga uno por uno para comprobar que los demás siguen funcionando. Tarda unos 25 segundos (espera a que el cortocircuito se cierre).

## Tolerancia a fallos en Pedidos

- Timeout de 2 s y 2 reintentos por llamada.
- Cortocircuito: tras 3 fallos seguidos deja de llamar al servicio caído durante 15 s.
- Caché local con los últimos productos y clientes conocidos.
- Estados del pedido: `CONFIRMADO`, `CONFIRMADO_CON_CACHE`, `PENDIENTE_VALIDACION`, `RECHAZADO`.
- `POST /pedidos/revalidar` reprocesa los pedidos pendientes cuando el servicio vuelve.
