"""
Inicia los tres microservicios en procesos separados.
Uso:  python iniciar_servicios.py      (abre la interfaz web; Ctrl+C para detener)
Para simular una caída, cierre un servicio individual iniciándolos por
separado en tres terminales:  python productos/main.py  (etc.)
"""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
servicios = [("Productos", "productos/main.py", 8001),
             ("Clientes", "clientes/main.py", 8002),
             ("Pedidos", "pedidos/main.py", 8003)]
procesos = []
for nombre, ruta, puerto in servicios:
    procesos.append(subprocess.Popen([sys.executable, os.path.join(BASE, ruta)]))
    time.sleep(1)
    print(f"  {nombre:10} -> http://127.0.0.1:{puerto}/docs")
interfaz = Path(BASE, "interfaz", "index.html").as_uri()
webbrowser.open(interfaz)
print(f"\n  Interfaz   -> {interfaz}")
print("\nServicios activos. Presione Ctrl+C para detenerlos.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    for p in procesos:
        p.terminate()
    print("Servicios detenidos.")
