# Calendario — Rainmeter Widget

Un widget de escritorio para **Rainmeter** que muestra tu semana de Google Calendar (y tus tareas de Google Tasks) en formato horizontal (estilo "vista semanal" de Google Calendar), con eventos repartidos automáticamente en columnas cuando se solapan, y una paleta de colores personalizada por calendario.

El proyecto tiene dos partes que trabajan juntas:

1. **`actualitzar_calendari.py`** — script en Python que se conecta a la Google Calendar API y a la Google Tasks API, descarga los eventos y tareas de la semana actual de todos tus calendarios y listas de tareas, y los vuelca a un fichero de texto plano.
2. **Skin de Rainmeter** (`CalendariWidget.ini` + `parser.lua`) — lee ese fichero de texto y dibuja la rejilla semanal en el escritorio, calculando el layout y asignando colores según el calendario de origen de cada evento.

---

## Características

- Vista semanal horizontal (Lunes → Domingo), franja horaria de 07:00 a 23:00.
- Reparto automático de eventos solapados en columnas, igual que hace Google Calendar en su vista de semana/día (algoritmo *sweep-line*).
- Franja fija superior para eventos de "Todo el día".
- **Tareas de Google Tasks** con fecha límite: aparecen en la franja de "Todo el día" del día que vencen. Las completadas se muestran en gris apagado y con el prefijo "✓".
- Colores por calendario, en una paleta de rosas y marrones, con transparencia; el color del texto (blanco/negro) se elige automáticamente según el contraste de cada fondo.
- Soporte para eventos que cruzan la medianoche (se parten en dos bloques, uno por día).
- Lectura robusta de codificación (UTF-8 y UTF-16 con BOM).
- Actualización automática cada 60 segundos por parte del skin (lectura del fichero de texto); la descarga de Google Calendar y Google Tasks se ejecuta por separado (manual o programada).

---

## Arquitectura

```mermaid
flowchart TD
    A[Google Calendar API] -->|OAuth2 + Calendar API v3| B["actualitzar_calendari.py"]
    A2[Google Tasks API] -->|OAuth2 + Tasks API v1| T["obtenir_tasques()<br/>solo tareas con fecha límite<br/>pendiente → tag tasks<br/>completada → tag tasksfet + ✓"]
    T -->|una sola llamada por ejecución| B
    B -->|escribe| C[["esdeveniments_setmana.txt"<br/>UTF-8, un día por línea]]
    C -->|lee cada 60s| D["parser.lua<br/>(Script measure de Rainmeter)"]
    D -->|parsea líneas y asigna columnas/colores| E{"¿Eventos<br/>solapados?"}
    E -->|Sí| F[Algoritmo sweep-line:<br/>reparte en columnas]
    E -->|No| G[Una columna a ancho completo]
    D -->|eventos "Tot el dia" y tareas| K[Franja fija superior<br/>máx. MaxAllDay cajas por día]
    F --> H["SKIN:Bang('!SetOption', ...)<br/>posiciona y colorea cada caja"]
    G --> H
    K --> H
    H --> I["CalendariWidget.ini<br/>(Meters: Shape + String)"]
    I --> J[["Widget en el escritorio"]]

    style A fill:#e8c4d0,stroke:#8a4a5c,color:#2a1015
    style A2 fill:#e8c4d0,stroke:#8a4a5c,color:#2a1015
    style T fill:#f5e1d5,stroke:#8a4a5c,color:#2a1015
    style B fill:#a5613e,stroke:#5a2f1e,color:#fff
    style C fill:#f5e1d5,stroke:#8a4a5c,color:#2a1015
    style D fill:#a5613e,stroke:#5a2f1e,color:#fff
    style K fill:#f5e1d5,stroke:#8a4a5c,color:#2a1015
    style H fill:#8c463c,stroke:#4a2018,color:#fff
    style I fill:#f5e1d5,stroke:#8a4a5c,color:#2a1015
    style J fill:#e8c4d0,stroke:#8a4a5c,color:#2a1015
```

### Flujo resumido

1. **Autenticación** — `actualitzar_calendari.py` usa OAuth2 (`credentials.json` → `token.json`) para autenticarse contra Google con permisos de solo lectura. Los permisos (*scopes*) son tres: `calendar.readonly`, `calendar.calendarlist.readonly` y `tasks.readonly`.
2. **Descarga de eventos** — obtiene la lista de calendarios del usuario, y para cada uno, los eventos de la semana actual (lunes a domingo).
3. **Descarga de tareas** — Google Tasks **no forma parte de la Calendar API**: tiene su propia API, así que `obtenir_tasques()` lee por separado todas las listas de tareas y recoge las que tienen fecha límite dentro de la semana (pendientes y completadas). Se llama **una sola vez por ejecución**, fuera del bucle de calendarios.
4. **Clasificación por tag** — el nombre de cada calendario se compara contra `DICCIONARI_TAGS` para asignarle una etiqueta (`principal`, `horari`, `treball`, `gym`, `aniversaris`, `tasks`); si no coincide con ninguna palabra clave, se usa `principal` por defecto. Las tareas de Google Tasks no pasan por el diccionario: las pendientes llevan siempre el tag `tasks` y las completadas `tasksfet`.
5. **Serialización** — escribe `esdeveniments_setmana.txt`, un fichero UTF-8 con un día por línea, formato `NombreDia|evento1 # evento2 # ...`. Las tareas se escriben como eventos de "Tot el dia" (`Tot el dia - Título [tasks]`), porque Google Tasks solo guarda la fecha, no la hora.
6. **Lectura por Rainmeter** — `parser.lua` (medida `Script` dentro de `CalendariWidget.ini`) relee ese fichero en cada ciclo de `Update`.
7. **Layout** — por cada día, separa eventos de "todo el día" y tareas (franja fija arriba) de eventos con hora; a estos últimos les aplica el algoritmo de columnas para que los solapados se repartan en paralelo, igual que en Google Calendar.
8. **Render** — por cada evento, `parser.lua` llama a `SKIN:Bang('!SetOption', ...)` para mover, redimensionar, colorear y mostrar el par de *meters* `MeterEventBg_D_S` (fondo) y `MeterEvent_D_S` (texto) correspondientes a ese día (`D`) y slot (`S`).

---

## Estructura del repositorio

```
CalendariHoritzontal/
├── actualitzar_calendari.py     # Script Python: Google Calendar + Google Tasks -> fichero de texto
├── credentials.json             # (NO subir a git) credenciales OAuth de Google Cloud
├── token.json                   # (NO subir a git, se genera solo) token de sesión
├── esdeveniments_setmana.txt    # (generado) datos de la semana, leídos por el widget
└── @Resources/
    ├── CalendariWidget.ini      # Definición del skin de Rainmeter (meters)
    └── parser.lua               # Motor de parseig + layout + colores
```

> **Importante:** `credentials.json` y `token.json` contienen datos sensibles de tu cuenta de Google. Añádelos a `.gitignore` y no los subas nunca al repositorio.

---

## Paleta de colores por calendario

Definida en `parser.lua`, tabla `Colors` / `TextColors`. Todos los fondos llevan un punto de transparencia (canal alfa ≈ 84%) para integrarse con el fondo del escritorio; la excepción es `tasksfet`, más transparente a propósito para que parezca apagado.

| Tag (`DICCIONARI_TAGS`) | Calendario de ejemplo | Color de fondo (RGBA) | Color de texto |
|---|---|---|---|
| `principal` | Calendario principal / personal | `235,190,200,215` — rosa pastel | Negro |
| `horari` | Horario / clases | `185,90,110,215` — rosa vino | Blanco |
| `treball` | Trabajo / beca | `165,95,75,215` — terracota | Blanco |
| `gym` | Gimnasio | `140,70,60,215` — marrón rojizo | Blanco |
| `aniversaris` | Cumpleaños | `90,55,50,215` — marrón chocolate | Blanco |
| `tasks` | Tareas pendientes (Google Tasks) | `245,225,205,215` — beige/crema | Negro |
| `tasksfet` | Tareas completadas (Google Tasks) | `170,150,145,150` — gris rosado apagado | `70,60,60,255` — gris oscuro |
| *(desconocido)* | Cualquier otro | `120,95,95,190` (`ColorDefaultBg`) | Blanco (`ColorDefaultText`) |
| *(día libre)* | Sin eventos | `150,110,110,140` (`ColorBuit`) | Blanco roto (`ColorBuitText`) |

La regla de contraste es simple: si la luminosidad del fondo es alta (color claro), el texto va en negro; si es baja (color oscuro), el texto va en blanco. Para añadir o cambiar un color, edita ambas tablas (`Colors` y `TextColors`) a la vez para mantener la legibilidad.

> **Nombres de tag:** el parser solo reconoce tags formados por **letras** (patrón `%a+`). Un tag con guion bajo o números (por ejemplo `tasks_fet`) haría que esa línea se descartara en silencio. Por eso el tag de las completadas es `tasksfet`.

---

## Requisitos

- **Rainmeter** ≥ 4.3 (necesita soporte de *Script measures* con Lua y de *Shape meters*).
- **Python** 3.9+ para el script de sincronización.
- Dependencias de Python:
  ```bash
  pip install google-auth google-auth-oauthlib google-api-python-client
  ```
- Un proyecto en **Google Cloud Console** con la **Google Calendar API** y la **Google Tasks API** habilitadas, y credenciales OAuth de tipo *Desktop App* descargadas como `credentials.json`.

Ambas APIs son gratuitas y no requieren activar facturación; el uso de este widget (unas pocas decenas de peticiones por ejecución) queda muy lejos de las cuotas diarias.

---

## Instalación

1. **Clona o copia** este repositorio dentro de tu carpeta de skins de Rainmeter, normalmente:
   ```
   %USERPROFILE%\Documents\Rainmeter\Skins\CalendariHoritzontal\
   ```
2. **Configura Google Cloud:**
   - Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/).
   - Habilita la **Google Calendar API** y la **Google Tasks API** (*APIs y servicios → Biblioteca*).
   - Crea credenciales OAuth 2.0 de tipo "Aplicación de escritorio" y descarga el JSON como `credentials.json` en la raíz del proyecto.
3. **Instala las dependencias de Python** (ver sección de Requisitos).
4. **Ejecuta el script una vez** para autenticarte:
   ```bash
   python actualitzar_calendari.py
   ```
   Se abrirá el navegador para el login de Google; tras aceptar los permisos (calendario y tareas), se generará `token.json` (las siguientes ejecuciones ya no pedirán login, hasta que el token caduque).
   > Si ya tenías un `token.json` de una versión anterior sin soporte de tareas, **bórralo** antes de ejecutar: guarda los permisos antiguos y nunca pediría el permiso de Tasks.
5. **Verifica** que se ha creado `esdeveniments_setmana.txt` en la misma carpeta.
6. **Carga el skin en Rainmeter:** clic derecho en el icono de Rainmeter en la bandeja del sistema → *Manage* → busca `CalendariHoritzontal` → *Load*.
7. **(Opcional) Automatiza la sincronización** para que el widget se mantenga al día sin ejecutarlo a mano — por ejemplo con el Programador de tareas de Windows:
   ```
   Programador de tareas → Crear tarea básica
   Desencadenador: cada 30-60 minutos
   Acción: python.exe  C:\ruta\a\actualitzar_calendari.py
   ```

---

## Personalización

### Cambiar qué calendarios llevan qué tag

Edita `DICCIONARI_TAGS` en `actualitzar_calendari.py`. La clave es una palabra que se busca (en minúsculas) dentro del **nombre** del calendario en Google Calendar; el valor es el tag que se escribirá en el fichero de texto y que `parser.lua` usará para elegir el color:

```python
DICCIONARI_TAGS = {
    'principal':   'principal',
    'horari':      'horari',
    'treball':     'treball',
    'beca':        'treball',   # varios nombres de calendario -> mismo tag
    'gym':         'gym',
    'aniversaris': 'aniversaris',
    'tasks':       'tasks',
}
```

> Las tareas de **Google Tasks** no dependen de este diccionario: se leen por su propia API y usan siempre los tags `tasks` (pendiente) y `tasksfet` (completada).

### Cambiar la paleta de colores

Edita las tablas `Colors` y `TextColors` en `parser.lua`. Después de guardar, **haz un Refresh del skin en Rainmeter** (los scripts Lua no se recargan solos, ver sección de Troubleshooting).

### Cambiar horario visible, tamaño de columnas, etc.

Las constantes al inicio de `parser.lua` controlan el layout:

| Variable | Significado |
|---|---|
| `NumDies` | Número de columnas/días mostrados (7) |
| `MaxAllDay` | Franjas reservadas para eventos "todo el día" **y tareas** por columna (por defecto 4) |
| `MaxTimed` | Franjas reservadas para eventos con hora por columna (por defecto 4) |
| `AmpladaColumna` / `EspaiColumnes` | Ancho de cada columna de día y espacio entre ellas |
| `TimeStart` / `TimeEnd` | Rango horario visible (en minutos desde medianoche) |
| `PxPerMin` | Píxeles verticales por minuto (controla la "altura" de la rejilla) |

Dos cosas a tener en cuenta al tocar `MaxAllDay` / `MaxTimed`:

- **Meters por día:** `MaxEvents = MaxAllDay + MaxTimed` es el número de pares de meters (`MeterEventBg_D_S` / `MeterEvent_D_S`) que `CalendariWidget.ini` define por cada día (8 por defecto). Mientras la suma no supere los meters existentes, no hace falta tocar el `.ini`; si la superas, hay que añadir más meters por día. Los eventos que no caben en su franja no se muestran.
- **Posición de la rejilla:** el inicio de la rejilla horaria se calcula como `YGrid = YAllDayStart + MaxAllDay × AltAllDay + 6` (con los valores por defecto, `20 + 4 × 18 + 6 = 98`). El `.ini` tiene la rejilla escrita con coordenadas fijas (`FonsGraella`, las etiquetas `MeterHoraN` y las líneas `LiniaHoraN`), así que si cambias `MaxAllDay` debes desplazar esos elementos la misma cantidad de píxeles (18 px por cada franja de más o de menos).

---

## Troubleshooting

- **He cambiado `parser.lua` o el `.ini` y no se nota nada:** los scripts Lua no se recargan solos. Haz clic derecho sobre el skin → *Refresh skin*.
- **Las tareas no aparecen:**
  - Solo se muestran las tareas **con fecha límite** dentro de la semana actual; sin fecha no hay día donde ponerlas.
  - Comprueba que la **Google Tasks API** está habilitada en tu proyecto y que has borrado el `token.json` antiguo tras añadir el permiso de tareas.
  - Google Tasks solo guarda la fecha, no la hora, aunque la pongas en la web: por eso salen como "Tot el dia".
- **Las tareas salen repetidas varias veces:** la llamada a `obtenir_tasques()` debe estar **fuera** del bucle `for cal in calendars:` en `main()`. Si está dentro, se ejecuta una vez por calendario y cada tarea se duplica. Otra causa posible es tener un calendario llamado "Tasks" en tu lista de calendarios (tareas sincronizadas); en ese caso añade `or "tasks" in nom_cal` a la condición del `continue` que salta los calendarios de `contacts` y `holiday`.
- **Una tarea completada se ve con caracteres extraños:** no uses el tachado Unicode (`U+0336`); Rainmeter no lo dibuja bien. Las completadas se distinguen con el prefijo "✓ " y el color gris de `tasksfet`. Si el "✓" no se ve bien con tu fuente, cámbialo por `[x] ` u `OK `.
- **Un evento o tarea no aparece en su día:** puede haberse superado `MaxAllDay` (eventos de todo el día y tareas) o `MaxTimed` (eventos con hora) para ese día. Aumenta el valor correspondiente (ver *Personalización*).
- **Una línea del fichero se ignora:** comprueba que el tag solo tiene letras (nada de guiones bajos ni números) y que tiene color definido en `Colors` / `TextColors`.
- **Error 403 `access_denied` al autenticarte:** tu app está en modo *Testing* y tu cuenta no figura como usuario de prueba. En Google Cloud Console ve a *Google Auth Platform → Público → Usuarios de prueba* y añade tu correo.
- **Tengo que volver a autenticarme cada semana:** mientras la app esté en modo *Testing*, Google caduca el token de actualización a los 7 días. En *Google Auth Platform → Público* puedes pulsar *Publicar la aplicación*; al ser de uso personal no hace falta verificarla, y el token deja de caducar.
- **Aviso "Aplicación no verificada" en el navegador:** es normal en proyectos personales. Pulsa *Avanzado → Ir a (nombre del proyecto)* y acepta.

---

## Ejemplo semana casual
![alt text](image-1.png)
---