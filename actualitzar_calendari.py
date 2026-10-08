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

# IMPORTANT: canvia això per la ruta real de la teva skin de Rainmeter.
# Si el .py ja viu dins la carpeta de la skin, la línia de sota ja fa la feina sola.
RUTA_SORTIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'esdeveniments_setmana.txt')
# Alternativa manual:
# RUTA_SORTIDA = r"C:\Users\ELTEUUSUARI\Documents\Rainmeter\Skins\CalendariHoritzontal\esdeveniments_setmana.txt"


def obtenir_setmana_actual():
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    return [dilluns + datetime.timedelta(days=i) for i in range(7)]

def obtenir_tasques(creds, dies_setmana):
    """Retorna una llista de (data 'YYYY-MM-DD', títol) per a les tasques
    amb data límit dins de la setmana."""
    service_tasks = build('tasks', 'v1', credentials=creds)
    dates_valides = {d.strftime('%Y-%m-%d') for d in dies_setmana}

    # Marge d'un dia a cada banda: Tasks guarda la data com a mitjanit UTC
    # i així evitem perdre tasques per diferències de zona horària.
    due_min = (dies_setmana[0] - datetime.timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
    due_max = (dies_setmana[-1] + datetime.timedelta(days=1)).strftime('%Y-%m-%dT23:59:59Z')

    resultat = []
    try:
        llistes = service_tasks.tasklists().list(maxResults=100).execute().get('items', [])
    except Exception as e:
        print(f"Avís: no s'han pogut llegir les llistes de tasques: {e}")
        return resultat

    for llista in llistes:
        page_token = None
        while True:
            try:
                resp = service_tasks.tasks().list(
                    tasklist=llista['id'],
                    dueMin=due_min,
                    dueMax=due_max,
                    showCompleted=True,
                    showHidden=True,
                    maxResults=100,
                    pageToken=page_token,
                ).execute()
            except Exception as e:
                print(f"Avís: no s'han pogut llegir tasques de '{llista.get('title')}': {e}")
                break

            for t in resp.get('items', []):
                due = t.get('due')
                if not due:
                    continue  # sense data límit no es pot ubicar en cap dia
                data = due[:10]
                if data in dates_valides:
                    feta = t.get('status') == 'completed'
                    resultat.append((data, t.get('title', '(sense títol)'), feta))

            page_token = resp.get('nextPageToken')
            if not page_token:
                break
    return resultat

def tatxar(text):
    return ''.join(c + '\u0336' for c in text)

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
    dies_setmana = obtenir_setmana_actual()
    time_min = datetime.datetime.combine(dies_setmana[0], datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(dies_setmana[-1], datetime.time.max).isoformat() + 'Z'

    try:
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
    except Exception as e:
        print(f"Error obtenint la llista de calendaris: {e}")
        return

    calendari_setmana = {dia.strftime('%Y-%m-%d'): [] for dia in dies_setmana}

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

                titol = event.get('summary', '(sense títol)')

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
    
    for data, titol, feta in obtenir_tasques(creds, dies_setmana):
        if feta:
            calendari_setmana[data].append((None, None, "X " + titol, 'tasksfet'))
        else:
            calendari_setmana[data].append((None, None, titol, 'tasks'))

    noms_dies = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres", "Dissabte", "Diumenge"]

    # Escrivim SEMPRE en UTF-8 (el widget de Rainmeter espera CodePage=65001)
    with open(RUTA_SORTIDA, "w", encoding="utf-8", newline="\n") as f:
        for i, dia_obj in enumerate(dies_setmana):
            data_str = dia_obj.strftime('%Y-%m-%d')
            llista_events = sorted(
                calendari_setmana[data_str],
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

            dia_setmana_text = f"{noms_dies[i]} {dia_obj.strftime('%d/%m')}"
            f.write(f"{dia_setmana_text}|{text_cadena}\n")

    print("Fitxer generat correctament (UTF-8):", RUTA_SORTIDA)


if __name__ == '__main__':
    main()