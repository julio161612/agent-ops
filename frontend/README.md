# Agent Ops — Frontend

Panel de administración de Agent Ops: React 19 + TypeScript + Vite + Tailwind CSS 4,
consumiendo directamente la API del [backend](../backend). Consulta el
[README raíz](../README.md) para la visión de producto completa y el diagrama
de arquitectura.

> Para simplemente ver la aplicación completa funcionando (sin hot-reload),
> el camino más corto es `docker compose up --build` desde la raíz del repo —
> levanta este frontend ya compilado y servido por nginx junto con el
> backend, Postgres y Redis, todo con un solo comando. Lo de abajo es para
> desarrollar sobre el frontend con recarga en caliente.

## Stack

- **Vite** + **React 19** + **TypeScript** (`strict`, sin `any` implícitos)
- **Tailwind CSS 4** (tokens en `src/index.css` vía `@theme`, sin `tailwind.config.js`)
- **React Router 7** para el enrutado
- **TanStack Query 5** para todo el estado de servidor (fetch, cache, invalidación)
- **React Hook Form + Zod** para formularios y validación
- **Radix UI** (primitivas sin estilo: Dialog, Select, Tabs, DropdownMenu, Toast, Switch) +
  componentes propios en `src/components/ui/` — no se usa una librería de componentes
  completa (shadcn/MUI/etc.), para tener control total del diseño con Tailwind puro
- **Recharts** para los gráficos del dashboard y métricas
- **lucide-react** para iconos (SVG, nunca emojis)

## Arrancar en local (junto al backend)

El backend debe estar corriendo primero (ver [`../backend/README.md`](../backend/README.md)):

```bash
# Terminal 1 — backend
cd ../backend
docker compose up -d postgres redis   # o desde la raíz del monorepo
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Por defecto Vite corre en `http://localhost:5173` y su proxy de desarrollo reenvía
`/api/*` a `http://localhost:8000` (configurado en `vite.config.ts`), así que el
frontend nunca necesita saber la URL real del backend en desarrollo — ni sufre CORS.

Si tu backend corre en otro puerto, cambia el `target` del proxy en `vite.config.ts`,
o define `VITE_API_BASE_URL` (por ejemplo `http://localhost:8010/api/v1`) en un
`.env.local` para saltarte el proxy por completo.

Abre `http://localhost:5173/register` y crea un tenant nuevo — empieza automáticamente
en el plan Free (Fase 10).

## Estructura

```
src/
├── App.tsx                 # Definición de rutas (React Router)
├── main.tsx                 # Providers: QueryClient, Router, Toast, Auth
├── contexts/
│   └── AuthContext.tsx      # Sesión: login/registro/logout, usuario/tenant actual, hasRole()
├── lib/
│   ├── api/
│   │   ├── client.ts         # fetch wrapper: headers, errores tipados, refresh de token
│   │   ├── tokenStore.ts     # persistencia de tokens (localStorage) + evento de logout
│   │   ├── types.ts          # Tipos TS espejo de los schemas Pydantic del backend
│   │   └── endpoints/        # Un archivo por recurso (agents.ts, billing.ts, ...)
│   ├── queryKeys.ts          # Claves de TanStack Query centralizadas
│   └── utils.ts              # cn(), formatCurrency(), formatDate(), etc.
├── components/
│   ├── ui/                   # Primitivas de diseño (Button, Card, Dialog, Table, ...)
│   ├── layout/                # Sidebar, Header, AppLayout, guardas de ruta
│   └── dashboard/             # Componentes específicos del dashboard (StatCard, gráfico)
└── pages/                    # Una carpeta por sección de la navegación
    ├── auth/                  agents/          routing/         guardrails/
    ├── escalations/            traces/          metrics/         billing/
    ├── users/                  integrations/    settings/
```

## Decisiones de arquitectura

- **Cliente API tipado a mano, no generado desde OpenAPI**: los tipos en
  `lib/api/types.ts` reflejan uno a uno los schemas Pydantic del backend (catalogados
  explorando cada router). Se descartó generar el cliente desde `/openapi.json` porque
  con ~20 recursos y este alcance de una sola vez, la generación automática añade una
  dependencia y un paso de build extra sin ahorrar tiempo real; mantenerlos a mano es
  además lo que permite que cada función de `endpoints/*.ts` tenga una firma ergonómica
  (`agentsApi.test(id, content)` en vez de un cliente genérico `POST /agents/{id}/test`).

- **Interceptor de refresh de token**: el backend no exponía `POST /auth/refresh` — sí
  tenía el schema `RefreshRequest` ya definido pero sin endpoint ni servicio detrás. Como
  la Fase 11 pide explícitamente un interceptor que renueve el token automáticamente, se
  añadió `auth_service.refresh_tokens` + el endpoint en el backend (con rotación de
  refresh token en cada uso) — la única modificación de backend en esta fase, documentada
  aquí porque se desvía de "solo frontend". `lib/api/client.ts` engancha cualquier 401 no
  proveniente del propio login/refresh, intenta renovar una sola vez (una promesa
  compartida evita ráfagas de refresh en paralelo si varias peticiones fallan a la vez), y
  si el refresh también falla, limpia la sesión y notifica a `AuthContext` para redirigir
  a `/login`.

- **Tokens en `localStorage`**, no en cookie httpOnly: es el trade-off estándar de una SPA
  pura sin backend-for-frontend — simple de implementar y suficiente para una demo, pero
  técnicamente expuesto a robo vía XSS si algún día se renderiza HTML no confiable. Una
  versión de producción real pondría el refresh token detrás de una cookie httpOnly
  emitida por un BFF; queda fuera de alcance y se señala aquí en vez de callarlo.

- **Guardas de rol en dos capas**: `Sidebar`/`MobileNav` ocultan enlaces según
  `hasRole()` (UX — no muestres lo que no puedes usar), y `RequireRole` en `App.tsx`
  bloquea la ruta `/users` a nivel de router (seguridad real — nunca confiar solo en
  ocultar un botón). El resto de páginas son visibles para cualquier rol autenticado
  porque cada acción de mutación (crear/editar/borrar) se oculta individualmente con
  `hasRole("operator")` / `hasRole("admin")`, dejando la vista de solo lectura disponible
  para `viewer` — reflejando la misma matriz de permisos de la Fase 8.

- **Sin librería de componentes preconstruida**: los primitivos de `components/ui/` están
  escritos a mano sobre Radix (accesibilidad: foco, ARIA, Escape, click-outside ya
  resueltos) + Tailwind (todo el estilo). Es más código que instalar shadcn/MUI, pero da
  control total sobre el diseño pedido ("no un dashboard genérico de bootstrap") sin pelear
  contra las convenciones de una librería ajena.

- **El frontend no reinventa reglas de negocio**: no recalcula nada de
  facturación/límites — todos los números (uso actual, comparación de planes, facturas)
  vienen tal cual de la API, que ya es la fuente de verdad (Fase 10). El diálogo de
  cambio de plan simplemente muestra el mismo criterio de "sin prorrateo" que ya
  documenta el backend.

## Calidad

```bash
npx tsc -b --noEmit   # type-check estricto, sin emitir
npm run build          # build de producción (incluye el type-check anterior)
npm run lint            # oxlint
```

No hay tests automatizados de frontend en esta fase (fuera del alcance pedido) — la
verificación se hizo manualmente contra el backend real, recorriendo cada sección con el
navegador.
