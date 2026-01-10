# Lebrun Web (Demo para Cliente)

Este paquete permite probar avances de la migración en el equipo del cliente.

## Concepto

- El **servidor web** (FastAPI) se conecta a la base de datos.
- La **impresora fiscal por COM (TFHKA)** se ejecuta desde un **Fiscal Agent** (servicio Windows) instalado en la PC que tiene el SDK/driver y el puerto COM.
- El servidor solo **encola trabajos** (ej: Reporte X/Z). El agente hace _pull_ y ejecuta en local.

---

## Modo 1: Todo en una PC (LOCAL)

### 6 comandos (PowerShell)

1. `cd "C:\Ruta\Lebrun-Py"`
2. `copy .env.demo-local.example .env`
3. `notepad .env`
4. `.\scripts\demo\server-install.ps1`
5. `.\scripts\demo\server-run.ps1`
6. En otra consola (Admin): `cd fiscal-agent; .\install-service.ps1 -BaseUrl "http://127.0.0.1:8000" -Token "<TOKEN>" -Caja "01"`

Luego abrir en el navegador: `http://127.0.0.1:8000`

---

## Modo 2: Servidor central + PC fiscal (LAN)

### En el SERVIDOR (PC/VM en la LAN)

1. `cd "C:\Ruta\Lebrun-Py"`
2. `copy .env.demo-server.example .env`
3. `notepad .env`
4. `.\scripts\demo\server-install.ps1`
5. `.\scripts\demo\server-run.ps1`

Firewall (si aplica): permitir TCP 8000 entrante.

### En la PC FISCAL (donde está TFHKA + COM)

6. En PowerShell (Admin):
   `cd "C:\Ruta\Lebrun-Py\fiscal-agent"`
   `copy agent.env.example agent.env`
   `notepad agent.env`
   `.
\install-service.ps1 -BaseUrl "http://IP_DEL_SERVIDOR:8000" -Token "<TOKEN>" -Caja "01"`

Luego el cliente navega a: `http://IP_DEL_SERVIDOR:8000`

---

## Verificación rápida

- En la web: ir a **Facturación → Reportes Z/X** y emitir X o Z.
- El servidor encola el job.
- El agente (servicio) debe registrar ejecución en `fiscal-agent\logs\stdout.log`.

---

## Notas

- `LEBRUN_FISCAL_AGENT_TOKEN` debe ser el mismo en servidor y agente.
- Recomendado: **un servicio por caja** (filtrado con `LEBRUN_FISCAL_CAJA`).
- La integración real TFHKA/COM se implementa dentro de `fiscal-agent/agent.py` (por ahora es stub).
