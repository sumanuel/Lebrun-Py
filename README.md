# Lebrun-Py (migración Web)

Este proyecto es el **scaffold** para migrar el WinForms `lebrun` a una aplicación **Web en Python**, manteniendo la organización por módulos (bancos/clientes/contabilidad/facturación/etc) pero con una estructura más mantenible.

## Objetivo de arquitectura

- **Web** (monolito liviano): FastAPI + plantillas (Jinja2) para páginas y endpoints.
- **Capas** claras:
  - `modules/*` = casos de uso del negocio por módulo (auth, bancos, clientes, ...)
  - `db/*` = conexión y selección de base (sysadm/sysconf/sysconta_XX)
  - `core/*` = configuración, seguridad, logging
  - `web/*` = templates y assets

Esto refleja tu estructura actual:

- `clasesData/*` → `app/db/*` y `app/core/*`
- `clases/<modulo>/*` → `app/modules/<modulo>/*` (service/repository/schemas)
- `formularios/<modulo>/*` → `app/web/templates/<modulo>/*` (o vistas) + routers

## Bases de datos (equivalente a App.config)

En C# usas:

- `db1 = sisadm`
- `db2 = sysconf`
- `db3 = sysconta` (con sufijo por compañía: `sysconta_02`, etc)

En Python lo modelamos con variables de entorno.

### Variables de entorno

Crea un `.env` basado en `.env.example`.

- `LEBRUN_DB_HOST`, `LEBRUN_DB_PORT`, `LEBRUN_DB_USER`, `LEBRUN_DB_PASSWORD`
- `LEBRUN_DB_SYSADM` (db1), `LEBRUN_DB_SYSCONF` (db2), `LEBRUN_DB_SYSCONTA_PREFIX` (db3)
- `SECRET_KEY` (sesiones)

## Cómo correr (dev)

1. Crear venv e instalar deps:

- `python -m venv .venv`
- `./.venv/Scripts/Activate.ps1`
- `pip install -r requirements.txt`

2. Crear `.env`:

- Copia `.env.example` a `.env` y ajusta credenciales.

3. Ejecutar:

- `uvicorn app.main:app --reload`

Luego abre:

- `http://127.0.0.1:8000/login`

## Qué incluye hoy

- Página `/login` (lista compañías desde `sysconf.confdatosempresa`)
- POST `/login` (validación básica contra `sysconf.confusuario`)
- Página `/` (renderiza menú dinámico desde `conf_menu/confmapamenu`)

Credenciales de prueba (según tu BD):

- Usuario: `caja1`
- Password: `sisi`

## Siguiente paso recomendado

Migrar por “vertical slices”:

1. Auth + compañías + menú (equivalente a `frmLogin` + `Principal.cargarMenuPrincipal`)
2. Bancos
3. Clientes
4. Contabilidad
5. Facturación/SENIAT

Si quieres, en el próximo paso puedo:

- Implementar el **menú dinámico** leyendo `conf_menu`/`confmapamenu` (tal como en C#),
- y dejar rutas/vistas por módulo (bancos/clientes/etc) listas.
