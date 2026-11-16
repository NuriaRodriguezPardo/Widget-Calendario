import datetime
import os.path
import re
import sys
import unicodedata
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.calendarlist.readonly',
    'https://www.googleapis.com/auth/tasks.readonly',
]

# Mapa de "paraula al nom del calendari" -> "tag" que fem servir al fitxer de sortida.
# Els tags han de coincidir EXACTAMENT amb les claus de la taula Colors del parser.lua
DICCIONARI_TAGS = {
    'principal':   'principal',
    'horari':      'horari',
    'treball':     'treball',
    'gym':         'gym',
    'aniversaris': 'aniversaris',
    'tasks':       'tasks',
}

# A la columna de la setmana vinent NOMÉS hi surten els esdeveniments d'aquests tags
# (calendari principal + tasques). La resta de calendaris no s'hi mostren.
TAGS_SETMANA_VINENT = {'principal', 'tasks', 'tasksfet', 'aniversaris'}

# Un esdeveniment del calendari principal el títol del qual COMENÇA per una d'aquestes paraules
# es marca amb el tag 'aniversaris' (encara que no existeixi cap calendari amb aquest nom).
# No distingeix majúscules ni accents: "Cumpleaños", "cumpleanos", "CUMPLE", "Aniversari",
# "Birthday"... També accepta el plural ("Aniversaris") i un emoji o símbol al davant ("🎂 Cumple").
PREFIXOS_ANIVERSARI = ['aniversari', 'cumpleaños', 'cumple', 'birthday']

# IMPORTANT: canvia això per la ruta real de la teva skin de Rainmeter.
# Si el .py ja viu dins la carpeta de la skin, la línia de sota ja fa la feina sola.
RUTA_SORTIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'esdeveniments_setmana.txt')
# Alternativa manual:
# RUTA_SORTIDA = r"C:\Users\ELTEUUSUARI\Documents\Rainmeter\Skins\CalendariHoritzontal\esdeveniments_setmana.txt"

# token.json i credentials.json es busquen SEMPRE a la carpeta de l'script,
# vagis d'on vagis a executar-lo (VS Code, terminal, Programador de tasques...).
CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_TOKEN = os.path.join(CARPETA, 'token.json')
RUTA_CREDENCIALS = os.path.join(CARPETA, 'credentials.json')

NOMS_DIES = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres", "Dissabte", "Diumenge"]


def configurar_consola():
    """Evita que un accent, una ñ, una ç o qualsevol símbol raro faci petar un print()
    quan la consola/redirecció de Windows no és UTF-8 (p. ex. al Programador de tasques):
    el que no es pugui representar es mostra com a '?' en lloc de donar error."""
    for flux in (sys.stdout, sys.stderr):
        if flux is not None and hasattr(flux, 'reconfigure'):
            try:
                flux.reconfigure(errors='replace')
            except Exception:
                pass


def obtenir_credencials():
    """Retorna credencials vàlides. Si el token ha caducat o Google l'ha revocat
    (invalid_grant), demana login un cop més sense haver d'esborrar token.json a mà."""
    creds = None
    if os.path.exists(RUTA_TOKEN):
        creds = Credentials.from_authorized_user_file(RUTA_TOKEN, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            print(f"Avís: el token ja no és vàlid ({e}). Cal tornar a iniciar sessió.")
            creds = None
    else:
        creds = None   # sense token, o token sense refresh_token

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(RUTA_CREDENCIALS, SCOPES)
        # prompt='consent' força que Google doni SEMPRE un refresh_token nou;
        # sense això, si ja havies autoritzat l'app, pot no tornar-lo a donar.
        creds = flow.run_local_server(port=0, prompt='consent')

    with open(RUTA_TOKEN, 'w', encoding='utf-8') as token:
        token.write(creds.to_json())
    return creds


def obtenir_setmanes(n=2):
    """Retorna els dies de la setmana actual i de les n-1 següents (dilluns -> diumenge)."""
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    return [dilluns + datetime.timedelta(days=i) for i in range(7 * n)]


def neteja(text):
    """Evita que un títol trenqui el format del fitxer: sense salts de línia
    i sense '#', que és el separador d'esdeveniments.

    A més, el passa a forma NFC (lletra + accent en un sol caràcter: à é í ï ò ú ü ç ñ l·l...).
    Els textos escrits des d'un mòbil o un Mac poden arribar amb l'accent com a caràcter
    separat, i aleshores es dibuixa desplaçat o com a un quadradet al widget."""
    text = unicodedata.normalize('NFC', text)
    return ' '.join(text.replace('#', '\uff03').split())


def _sense_accents(text):
    """Minúscules i sense accents (à = a, ñ = n, ç = c) per comparar paraules."""
    descompost = unicodedata.normalize('NFD', text.casefold())
    return ''.join(c for c in descompost if not unicodedata.combining(c))


_RE_ANIVERSARI = re.compile(
    r"^[\W_]*(?:%s)s?(?![^\W\d_])" % '|'.join(
        re.escape(_sense_accents(p)) for p in sorted(PREFIXOS_ANIVERSARI, key=len, reverse=True)
    )
)


def tag_segons_titol(titol, tag):
    """Si l'esdeveniment és del calendari principal i el títol comença per 'Aniversari',
    'Cumple', 'Cumpleaños', 'Birthday'... el converteix en 'aniversaris'. Altrament, no el toca."""
    if tag == 'principal' and _RE_ANIVERSARI.match(_sense_accents(titol)):
        return 'aniversaris'
    return tag


def clau_alfabetica(text):
    """Clau per ordenar sense distingir majúscules ni accents (à = a, ç = c, ñ = n),
    perquè 'Àlgebra' o 'Ñoquis' no quedin després de 'Zoologia' (Python ordena per codi)."""
    descompost = unicodedata.normalize('NFD', text.casefold())
    return ''.join(c for c in descompost if not unicodedata.combining(c))


def _tasques_de_llista(service_tasks, llista, **filtres):
    """Recorre totes les pàgines de tasques d'una llista de Google Tasks."""
    page_token = None
    while True:
        try:
            resp = service_tasks.tasks().list(
                tasklist=llista['id'], maxResults=100, pageToken=page_token, **filtres
            ).execute()
        except Exception as e:
            print(f"Avís: no s'han pogut llegir tasques de '{llista.get('title')}': {e}")
            return
        for t in resp.get('items', []):
            yield t
        page_token = resp.get('nextPageToken')
        if not page_token:
            return


def obtenir_tasques(creds, dies):
    """Llegeix Google Tasks (API pròpia, no forma part de Calendar).

    Retorna dues llistes:
      - finestra: [(data 'YYYY-MM-DD', títol, feta)] amb data límit dins de `dies`
        (pendents i completades), per pintar-les al seu dia.
      - pendents: [(data 'YYYY-MM-DD', títol)] de TOTES les tasques no completades
        amb data límit (de qualsevol data), ordenades per data.
    """
    service_tasks = build('tasks', 'v1', credentials=creds)
    dates_valides = {d.strftime('%Y-%m-%d') for d in dies}

    # Marge d'un dia a cada banda: Tasks guarda la data com a mitjanit UTC
    # i així evitem perdre tasques per diferències de zona horària.
    due_min = (dies[0] - datetime.timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
    due_max = (dies[-1] + datetime.timedelta(days=1)).strftime('%Y-%m-%dT23:59:59Z')

    finestra = []
    pendents = []
    try:
        llistes = service_tasks.tasklists().list(maxResults=100).execute().get('items', [])
    except Exception as e:
        print(f"Avís: no s'han pogut llegir les llistes de tasques: {e}")
        return finestra, pendents

    for llista in llistes:
        # 1) Tasques de les dues setmanes (amb les completades)
        for t in _tasques_de_llista(service_tasks, llista, dueMin=due_min, dueMax=due_max,
                                    showCompleted=True, showHidden=True):
            due = t.get('due')
            if not due:
                continue  # sense data límit no es pot ubicar en cap dia
            data = due[:10]
            if data in dates_valides:
                feta = t.get('status') == 'completed'
                finestra.append((data, neteja(t.get('title') or '(sense títol)'), feta))

        # 2) Totes les pendents, sense límit de dates
        for t in _tasques_de_llista(service_tasks, llista, showCompleted=False, showHidden=False):
            due = t.get('due')
            if not due:
                continue
            pendents.append((due[:10], neteja(t.get('title') or '(sense títol)')))

    pendents.sort(key=lambda p: (p[0], clau_alfabetica(p[1]), p[1]))
    return finestra, pendents


def format_data_tasca(data):
    """'2026-10-12' -> '12/10' (amb l'any si no és l'actual: '12/10/27')."""
    d = datetime.date.fromisoformat(data)
    return d.strftime('%d/%m') if d.year == datetime.date.today().year else d.strftime('%d/%m/%y')


def escriure_fitxer(ruta, dies, calendari_setmana, tasques_pendents):
    """Format del fitxer:
         - 7 línies: setmana actual (tots els calendaris)   'Dilluns 05/10|...'
         - 7 línies: setmana vinent (només TAGS_SETMANA_VINENT)
         - N línies: totes les tasques pendents             'TASCA|12/10|Títol'
    """
    # Escrivim SEMPRE en UTF-8 (el widget de Rainmeter espera CodePage=65001)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        for i, dia_obj in enumerate(dies):
            data_str = dia_obj.strftime('%Y-%m-%d')
            events_dia = calendari_setmana[data_str]
            if i >= 7:
                events_dia = [ev for ev in events_dia if ev[3] in TAGS_SETMANA_VINENT]
            llista_events = sorted(
                events_dia,
                key=lambda ev: ('00:00' if ev[0] is None else ev[0])
            )

            if not llista_events:
                text_cadena = "Lliure (Sense esdeveniments)"
            else:
                blocs = []
                for hora_ini, hora_fi, titol, tag in llista_events:
                    if hora_ini is None:
                        blocs.append(f"Tot el dia - {titol} [{tag}]")
                    else:
                        blocs.append(f"{hora_ini}-{hora_fi} - {titol} [{tag}]")
                text_cadena = " # ".join(blocs)

            dia_setmana_text = f"{NOMS_DIES[i % 7]} {dia_obj.strftime('%d/%m')}"
            f.write(f"{dia_setmana_text}|{text_cadena}\n")

        for data, titol in tasques_pendents:
            f.write(f"TASCA|{format_data_tasca(data)}|{titol}\n")


def main():
    configurar_consola()
    creds = obtenir_credencials()

    service = build('calendar', 'v3', credentials=creds)
    dies = obtenir_setmanes(2)   # setmana actual + setmana vinent (14 dies)
    time_min = datetime.datetime.combine(dies[0], datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(dies[-1], datetime.time.max).isoformat() + 'Z'

    try:
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
    except Exception as e:
        print(f"Error obtenint la llista de calendaris: {e}")
        return

    calendari_setmana = {dia.strftime('%Y-%m-%d'): [] for dia in dies}

    for cal in calendars:
        cal_id = cal['id']
        nom_cal = cal.get('summary', '').lower()
        if "contacts" in cal_id or "holiday" in cal_id:
            continue

        tag = 'principal'
        for clau, valor in DICCIONARI_TAGS.items():
            if clau in nom_cal:
                tag = valor
                break
        try:
            events_result = service.events().list(
                calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                if 'dateTime' in event['start']:
                    data_ini = start[:10]
                    hora_ini = start[11:16]
                    end_dt = event['end'].get('dateTime', '')
                    data_fi = end_dt[:10] if end_dt else data_ini
                    hora_fi = end_dt[11:16] if end_dt else hora_ini
                else:
                    data_ini = start[:10]
                    data_fi = data_ini
                    hora_ini = None
                    hora_fi = None

                titol = neteja(event.get('summary', '(sense títol)'))
                tag_ev = tag_segons_titol(titol, tag)   # 'principal' -> 'aniversaris' si cal

                if hora_ini is None:
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((None, None, titol, tag_ev))
                elif data_fi == data_ini:
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((hora_ini, hora_fi, titol, tag_ev))
                else:
                    # L'esdeveniment travessa mitjanit: el partim en dos trossos,
                    # un per cada dia, perquè cada dia és una columna independent.
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((hora_ini, "23:59", f"{titol} (continua)", tag_ev))
                    if data_fi in calendari_setmana:
                        calendari_setmana[data_fi].append(("00:00", hora_fi, f"{titol} (acaba)", tag_ev))
        except Exception as e:
            print(f"Avís: no s'ha pogut llegir esdeveniments de '{nom_cal}': {e}")
            continue

    # Tasques: UNA sola crida fora del bucle de calendaris (si no, es dupliquen)
    tasques_finestra, tasques_pendents = obtenir_tasques(creds, dies)
    for data, titol, feta in tasques_finestra:
        if feta:
            calendari_setmana[data].append((None, None, "X " + titol, 'tasksfet'))
        else:
            calendari_setmana[data].append((None, None, titol, 'tasks'))

    escriure_fitxer(RUTA_SORTIDA, dies, calendari_setmana, tasques_pendents)

    print("Fitxer generat correctament (UTF-8):", RUTA_SORTIDA)


if __name__ == '__main__':
    main()