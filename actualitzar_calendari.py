import datetime
import os.path
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
TAGS_SETMANA_VINENT = {'principal', 'tasks', 'tasksfet'}

# IMPORTANT: canvia això per la ruta real de la teva skin de Rainmeter.
# Si el .py ja viu dins la carpeta de la skin, la línia de sota ja fa la feina sola.
RUTA_SORTIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'esdeveniments_setmana.txt')
# Alternativa manual:
# RUTA_SORTIDA = r"C:\Users\ELTEUUSUARI\Documents\Rainmeter\Skins\CalendariHoritzontal\esdeveniments_setmana.txt"

NOMS_DIES = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres", "Dissabte", "Diumenge"]


def obtenir_setmanes(n=2):
    """Retorna els dies de la setmana actual i de les n-1 següents (dilluns -> diumenge)."""
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    return [dilluns + datetime.timedelta(days=i) for i in range(7 * n)]


def neteja(text):
    """Evita que un títol trenqui el format del fitxer: sense salts de línia
    i sense '#', que és el separador d'esdeveniments."""
    return ' '.join(text.replace('#', '\uff03').split())


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

    pendents.sort()
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
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

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

                if hora_ini is None:
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((None, None, titol, tag))
                elif data_fi == data_ini:
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((hora_ini, hora_fi, titol, tag))
                else:
                    # L'esdeveniment travessa mitjanit: el partim en dos trossos,
                    # un per cada dia, perquè cada dia és una columna independent.
                    if data_ini in calendari_setmana:
                        calendari_setmana[data_ini].append((hora_ini, "23:59", f"{titol} (continua)", tag))
                    if data_fi in calendari_setmana:
                        calendari_setmana[data_fi].append(("00:00", hora_fi, f"{titol} (acaba)", tag))
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
