-- parser.lua
-- Motor de lectura + layout tipus "Google Calendar":
-- els esdeveniments amb hores que realment se superposen es reparteixen
-- en columnes dins de la mateixa columna del dia. Els de "Tot el dia"
-- van en una franja fixa a dalt.
-- A la dreta de la graella hi ha dos panells verticals:
--   * Setmana vinent (nomes calendari principal + tasques)
--   * Totes les tasques pendents (de qualsevol data)

NumDies   = 7
MaxAllDay = 4   -- caixes reservades per a esdeveniments de tot el dia
MaxTimed  = 8   -- caixes reservades per a esdeveniments amb hora (el .ini ha de tenir MaxAllDay+MaxTimed parelles de meters per dia)
MaxEvents = MaxAllDay + MaxTimed

AmpladaColumna = 150
EspaiColumnes  = 10
MargeEsquerre  = 40

TimeStart = 7 * 60    -- 07:00 en minuts des de mitjanit
TimeEnd   = 23 * 60   -- 23:00 en minuts des de mitjanit
PxPerMin  = 0.7

YAllDayStart = 20
AltAllDay    = 18
YGrid        = YAllDayStart + (MaxAllDay * AltAllDay) + 6
AltMinEvent  = 20

-- ===== Panells de la dreta (setmana vinent + totes les tasques) =====
-- Es colguen just a la dreta de la graella i fan la mateixa alcada que ella.
XFinalGraella = MargeEsquerre + NumDies * (AmpladaColumna + EspaiColumnes) - EspaiColumnes
AmpladaPanell = 240
XPropera      = XFinalGraella + 20       -- columna unica per als dos panells
XTasques      = XPropera
YPanell       = YGrid
AltPanell     = (TimeEnd - TimeStart) * PxPerMin
SeparacioPanells = 10
AltPropera    = math.floor((AltPanell - SeparacioPanells) / 2)
YPropera      = YPanell
-- YTasques      = YPanell + AltPropera + SeparacioPanells
-- Cerca aquestes línies al fitxer parser.lua i ajusta-les:
YTasques = YPanell + AltPropera + SeparacioPanells + 10
AltTasques = AltPanell - AltPropera - SeparacioPanells - 10

-- AltTasques    = AltPanell - AltPropera - SeparacioPanells
AltFila       = 18      -- alcada de cada fila (caixa de 16 + 2 d'espai)
EspaiDia      = 6       -- espai extra abans de la capcalera de cada dia
PoolFiles     = 37      -- parelles de meters que hi ha al .ini per panell (MeterProp_1..37, MeterTasca_1..37)

-- Paleta de rosas y marrones, con un punto de transparencia (alpha ~215)
Colors = {
    principal   = "235,190,200,215",  -- Rosa pastel (Núria / Principal)
    horari      = "185,90,110,215",   -- Rosa envellutat / vinos
    treball     = "165,95,75,215",    -- Terracota
    gym         = "140,70,60,215",    -- Marró vermellós fosc
    aniversaris = "90,55,50,215",     -- Marró xocolata fosc
    tasks       = "245,225,205,215",  -- Beix / crema clar
    tasksfet    = "170,150,145,150",  -- Gris rosat apagat (tasca feta)
}
-- Color de texto (blanco o negro) según el que mejor contrasta con cada fondo
TextColors = {
    principal   = "20,20,20,255",     -- fons clar -> lletres negres
    horari      = "255,255,255,255",  -- fons fosc -> lletres blanques
    treball     = "255,255,255,255",  -- fons fosc -> lletres blanques
    gym         = "255,255,255,255",  -- fons fosc -> lletres blanques
    aniversaris = "255,255,255,255",  -- fons fosc -> lletres blanques
    tasks       = "20,20,20,255",     -- fons clar -> lletres negres
    tasksfet    = "70,60,60,255",     -- text gris fosc
}
ColorBuit         = "150,110,110,140"  -- Fons per a dies lliures (marró rosat suau)
ColorBuitText     = "235,225,220,255"
ColorDefaultBg    = "120,95,95,190"    -- Fons per a tags desconeguts (dins de la paleta)
ColorDefaultText  = "245,240,238,255"
ColorPanell         = "15,15,20,120"      -- Fons dels panells de la dreta (com la graella)
ColorCapcalera      = "120,85,95,215"     -- Capcalera de cada dia a la columna de la setmana vinent
ColorCapceleraText  = "255,255,255,255"

local function Utf16ToUtf8(data, littleEndian)
    -- Conversió senzilla UTF-16 -> UTF-8 (només calen caràcters del pla bàsic,
    -- suficient per a lletres catalanes/castellanes accentuades)
    local out = {}
    local i = 1
    local len = #data
    while i + 1 <= len do
        local b1, b2 = data:byte(i), data:byte(i + 1)
        local code
        if littleEndian then
            code = b2 * 256 + b1
        else
            code = b1 * 256 + b2
        end
        if code < 0x80 then
            table.insert(out, string.char(code))
        elseif code < 0x800 then
            table.insert(out, string.char(0xC0 + math.floor(code / 64), 0x80 + code % 64))
        else
            table.insert(out, string.char(
                0xE0 + math.floor(code / 4096),
                0x80 + math.floor(code / 64) % 64,
                0x80 + code % 64))
        end
        i = i + 2
    end
    return table.concat(out)
end

local function LlegirContingut(ruta)
    local f = io.open(ruta, "rb")
    if not f then return nil end
    local raw = f:read("*a")
    f:close()
    if not raw or #raw == 0 then return "" end

    local b1, b2, b3 = raw:byte(1), raw:byte(2), raw:byte(3)
    if b1 == 0xFF and b2 == 0xFE then
        return Utf16ToUtf8(raw:sub(3), true)
    elseif b1 == 0xFE and b2 == 0xFF then
        return Utf16ToUtf8(raw:sub(3), false)
    elseif b1 == 0xEF and b2 == 0xBB and b3 == 0xBF then
        return raw:sub(4)
    else
        return raw
    end
end

function Initialize()
    Dies = {}
    Tasques = {}
end

local function minutsDes(hhmm)
    local h, m = hhmm:match("^(%d%d):(%d%d)$")
    if not h then return nil end
    return tonumber(h) * 60 + tonumber(m)
end

-- Assigna columnes a esdeveniments que realment se superposen en el temps
-- (sweep-line + assignació greedy de columnes, el mateix principi que fa
-- servir Google Calendar per repartir events en la vista de dia/setmana)
local function AssignarColumnes(timed)
    table.sort(timed, function(a, b) return a.startMin < b.startMin end)
    local n = #timed
    local i = 1
    while i <= n do
        local maxEnd = timed[i].endMin
        local clusterEnd = i
        local j = i + 1
        while j <= n and timed[j].startMin < maxEnd do
            if timed[j].endMin > maxEnd then maxEnd = timed[j].endMin end
            clusterEnd = j
            j = j + 1
        end

        local colEnds = {}
        for k = i, clusterEnd do
            local col = nil
            for c = 1, #colEnds do
                if colEnds[c] <= timed[k].startMin then
                    col = c
                    break
                end
            end
            if not col then
                table.insert(colEnds, timed[k].endMin)
                col = #colEnds
            else
                colEnds[col] = timed[k].endMin
            end
            timed[k].col = col
        end
        for k = i, clusterEnd do
            timed[k].numCols = #colEnds
        end

        i = clusterEnd + 1
    end
    return timed
end

local function PosarCaixa(nomBg, nomTxt, x, y, w, h, text, bgColor, txtColor, estil)
    SKIN:Bang('!SetOption', nomBg, 'X', x)
    SKIN:Bang('!SetOption', nomBg, 'Y', y)
    SKIN:Bang('!SetOption', nomBg, 'Shape',
        'Rectangle 0,0,' .. w .. ',' .. h .. ',6 | Fill Color ' .. bgColor .. ' | StrokeWidth 0')
    SKIN:Bang('!SetOption', nomBg, 'Hidden', '0')
    SKIN:Bang('!UpdateMeter', nomBg)

    SKIN:Bang('!SetOption', nomTxt, 'X', x)
    SKIN:Bang('!SetOption', nomTxt, 'Y', y)
    SKIN:Bang('!SetOption', nomTxt, 'W', w)
    SKIN:Bang('!SetOption', nomTxt, 'H', h)
    SKIN:Bang('!SetOption', nomTxt, 'Text', text)
    SKIN:Bang('!SetOption', nomTxt, 'FontColor', txtColor)
    if estil then SKIN:Bang('!SetOption', nomTxt, 'StringStyle', estil) end
    SKIN:Bang('!SetOption', nomTxt, 'Hidden', '0')
    SKIN:Bang('!UpdateMeter', nomTxt)
end

local function AmagarParella(nomBg, nomTxt)
    SKIN:Bang('!SetOption', nomBg, 'Hidden', '1')
    SKIN:Bang('!UpdateMeter', nomBg)
    SKIN:Bang('!SetOption', nomTxt, 'Hidden', '1')
    SKIN:Bang('!UpdateMeter', nomTxt)
end

local function ColocarCaixa(d, s, x, y, w, h, text, bgColor, txtColor)
    PosarCaixa('MeterEventBg_' .. d .. '_' .. s, 'MeterEvent_' .. d .. '_' .. s,
        x, y, w, h, text, bgColor, txtColor)
end

local function AmagarCaixa(d, s)
    AmagarParella('MeterEventBg_' .. d .. '_' .. s, 'MeterEvent_' .. d .. '_' .. s)
end

local function HHMM(min)
    return string.format("%02d:%02d", math.floor(min / 60), min % 60)
end

-- Pinta una llista de files (capcalera / esdeveniment / tasca) com a llista vertical
-- dins d'un panell. Si no hi caben totes, l'última fila diu "... +N més".
-- pref = 'Prop' o 'Tasca' (noms dels meters: Meter<pref>Bg_i / Meter<pref>_i)
local function PintarFiles(pref, x, w, files, yPanel, altPanel)
    local nBg  = 'Meter' .. pref .. 'Bg_'
    local nTxt = 'Meter' .. pref .. '_'
    local yMax = yPanel + altPanel
    local maxFiles = math.min(PoolFiles, math.floor(altPanel / AltFila))

    local pos = {}
    local y = yPanel
    for idx, f in ipairs(files) do
        if f.cap and idx > 1 then y = y + EspaiDia end
        if idx > maxFiles or y + AltFila - 2 > yMax then break end
        pos[idx] = y
        y = y + AltFila
    end

    local fit = #pos
    local visibles = fit
    local resta = 0
    if fit < #files then
        visibles = math.max(fit - 1, 0)
        for idx = visibles + 1, #files do
            if not files[idx].cap then resta = resta + 1 end
        end
    end

    for idx = 1, visibles do
        local f = files[idx]
        local bg, fg, estil
        if f.cap then
            bg, fg, estil = ColorCapcalera, ColorCapceleraText, 'Bold'
        elseif f.lliure then
            bg, fg, estil = ColorBuit, ColorBuitText, 'Normal'
        else
            bg = Colors[f.tag] or ColorDefaultBg
            fg = TextColors[f.tag] or ColorDefaultText
            estil = 'Normal'
        end
        PosarCaixa(nBg .. idx, nTxt .. idx, x + 4, pos[idx], w - 8, AltFila - 2, f.text, bg, fg, estil)
    end

    local usades = visibles
    if visibles < #files and fit >= 1 then
        usades = visibles + 1
        PosarCaixa(nBg .. usades, nTxt .. usades, x + 4, pos[usades], w - 8, AltFila - 2,
            '... +' .. resta .. ' més', ColorBuit, ColorBuitText, 'Normal')
    end
    for s = usades + 1, PoolFiles do
        AmagarParella(nBg .. s, nTxt .. s)
    end
end

-- Files de la columna "setmana vinent": per a cada dia una capcalera i, sota,
-- els esdeveniments de tot el dia / tasques i els que tenen hora (ordenats).
local function FilesPropera()
    local files = {}
    if not Dies[NumDies + 1] then
        table.insert(files, { text = 'Sense dades (executa el script)', lliure = true })
        return files
    end
    for k = 1, NumDies do
        local dia = Dies[NumDies + k]
        if dia then
            table.insert(files, { cap = true, text = dia.titol })
            local n = 0
            for _, ev in ipairs(dia.allDay) do
                table.insert(files, { text = ev.text, tag = ev.tag })
                n = n + 1
            end
            table.sort(dia.timed, function(a, b)
                if a.startMin ~= b.startMin then return a.startMin < b.startMin end
                return a.text < b.text
            end)
            for _, ev in ipairs(dia.timed) do
                table.insert(files, { text = HHMM(ev.startMin) .. ' ' .. ev.text, tag = ev.tag })
                n = n + 1
            end
            if n == 0 then
                table.insert(files, { text = 'Lliure', lliure = true })
            end
        end
    end
    return files
end

-- Files de la columna "totes les tasques": data + titol, ja ordenades per l'script.
local function FilesTasques()
    local files = {}
    for _, t in ipairs(Tasques) do
        table.insert(files, { text = t.data .. '  ' .. t.text, tag = 'tasks' })
    end
    if #files == 0 then
        table.insert(files, { text = 'Cap tasca pendent', lliure = true })
    end
    return files
end

-- Fons i titols dels dos panells (la posicio surt de les constants de dalt)
local function PosicionarPanells()
    local function fons(nom, x, y, h)
        SKIN:Bang('!SetOption', nom, 'Shape',
            'Rectangle ' .. x .. ',' .. y .. ',' .. AmpladaPanell .. ',' .. h ..
            ' | Fill Color ' .. ColorPanell .. ' | StrokeWidth 0')
        SKIN:Bang('!UpdateMeter', nom)
    end
    fons('FonsPropera', XPropera, YPropera, AltPropera)
    fons('FonsTasques', XTasques, YTasques, AltTasques)

    local rang = ''
    local d1, d7 = Dies[NumDies + 1], Dies[2 * NumDies]
    if d1 and d7 then
        local a = d1.titol:match("(%d%d/%d%d)%s*$")
        local b = d7.titol:match("(%d%d/%d%d)%s*$")
        if a and b then rang = '  ' .. a .. ' - ' .. b end
    end
    SKIN:Bang('!SetOption', 'MeterTitPropera', 'X', XPropera)
    SKIN:Bang('!SetOption', 'MeterTitPropera', 'Y', YPropera - 22)
    SKIN:Bang('!SetOption', 'MeterTitPropera', 'Text', 'Setmana vinent' .. rang)
    SKIN:Bang('!UpdateMeter', 'MeterTitPropera')

    SKIN:Bang('!SetOption', 'MeterTitTasques', 'X', XTasques)
    SKIN:Bang('!SetOption', 'MeterTitTasques', 'Y', YTasques - 22)
    SKIN:Bang('!SetOption', 'MeterTitTasques', 'Text', 'Tasques pendents (' .. #Tasques .. ')')
    SKIN:Bang('!UpdateMeter', 'MeterTitTasques')
end

function Update()
    Dies = {}
    Tasques = {}
    local ruta = SKIN:GetVariable('CURRENTPATH') .. 'esdeveniments_setmana.txt'
    local contingut = LlegirContingut(ruta)

    if contingut == nil then
        SKIN:Bang('!SetOption', 'MeterTit1', 'Text', 'ERROR: no trobo esdeveniments_setmana.txt')
        SKIN:Bang('!UpdateMeter', 'MeterTit1')
        SKIN:Bang('!Redraw')
        return 0
    end

    local i = 0
    for linia in (contingut .. "\n"):gmatch("(.-)\n") do
        linia = linia:gsub("\r", "")
        if linia:sub(1, 6) == "TASCA|" then
            -- format tasca pendent: "TASCA|12/10|Titol"
            local dataT, textT = linia:match("^TASCA|([^|]*)|(.*)$")
            if textT then
                table.insert(Tasques, { data = dataT, text = textT })
            end
        elseif linia:match("%S") then
            i = i + 1
            local titol, dades = linia:match("^(.-)|(.*)$")
            local dia = { titol = titol or ("Dia " .. i), allDay = {}, timed = {} }
            if dades and not dades:match("^Lliure") then
                for tros in dades:gmatch("[^#]+") do
                    tros = tros:match("^%s*(.-)%s*$")
                    -- format horari: "07:00-08:30 - Titol [tag]"
                    local hIni, hFi, text, tag = tros:match("^(%d%d:%d%d)%-(%d%d:%d%d) %- (.-) %[(%a+)%]$")
                    if hIni then
                        local sMin = minutsDes(hIni)
                        local eMin = minutsDes(hFi)
                        if sMin then
                            if not eMin or eMin <= sMin then
                                -- Travessa mitjanit (p.ex. 15:00-10:00): com que cada
                                -- dia és una columna independent, el retallem fins al
                                -- final del dia en comptes de descartar-lo en silenci.
                                eMin = 23 * 60 + 59
                            end
                            table.insert(dia.timed, { startMin = sMin, endMin = eMin, text = text, tag = tag })
                        end
                    else
                        -- format tot el dia: "Tot el dia - Titol [tag]"
                        local text2, tag2 = tros:match("^Tot el dia %- (.-) %[(%a+)%]$")
                        if text2 then
                            table.insert(dia.allDay, { text = text2, tag = tag2 })
                        end
                    end
                end
            end
            Dies[i] = dia
        end
    end

    if #Dies == 0 then
        SKIN:Bang('!SetOption', 'MeterTit1', 'Text', 'ERROR: format de fitxer no reconegut')
        SKIN:Bang('!UpdateMeter', 'MeterTit1')
        SKIN:Bang('!Redraw')
        return 0
    end

    for d = 1, NumDies do
        local dia = Dies[d]
        local x = MargeEsquerre + (d - 1) * (AmpladaColumna + EspaiColumnes)

        SKIN:Bang('!SetOption', 'MeterTit' .. d, 'Text', dia and dia.titol or '')
        SKIN:Bang('!SetOption', 'MeterTit' .. d, 'FontColor', '0,0,0')
        SKIN:Bang('!SetOption', 'MeterTit' .. d, 'X', x)
        SKIN:Bang('!UpdateMeter', 'MeterTit' .. d)

        local slot = 1

        -- Esdeveniments de tot el dia: franja fixa a dalt de la columna
        if dia then
            for _, ev in ipairs(dia.allDay) do
                if slot > MaxAllDay then break end
                ColocarCaixa(d, slot,
                    x, YAllDayStart + (slot - 1) * AltAllDay,
                    AmpladaColumna - 6, AltAllDay - 2,
                    ev.text, Colors[ev.tag] or ColorDefaultBg, TextColors[ev.tag] or ColorDefaultText)
                slot = slot + 1
            end
        end
        while slot <= MaxAllDay do
            AmagarCaixa(d, slot)
            slot = slot + 1
        end

        -- Esdeveniments amb hora: es reparteixen en columnes si se superposen
        local buit = not dia or (#dia.timed == 0 and #dia.allDay == 0)

        if dia and #dia.timed > 0 then
            AssignarColumnes(dia.timed)
            for _, ev in ipairs(dia.timed) do
                if slot > MaxEvents then break end
                local sMin = math.max(ev.startMin, TimeStart)
                local eMin = math.min(ev.endMin, TimeEnd)
                local yEv = YGrid + (sMin - TimeStart) * PxPerMin
                local hEv = math.max(AltMinEvent, (eMin - sMin) * PxPerMin)
                local colW = AmpladaColumna / ev.numCols
                local xEv = x + (ev.col - 1) * colW

                ColocarCaixa(d, slot,
                    xEv, yEv,
                    colW - 4, hEv,
                    ev.text, Colors[ev.tag] or ColorDefaultBg, TextColors[ev.tag] or ColorDefaultText)
                slot = slot + 1
            end
        end

        if buit and slot <= MaxEvents then
            ColocarCaixa(d, slot,
                x, YGrid,
                AmpladaColumna - 6, AltMinEvent,
                'Lliure', ColorBuit, ColorBuitText)
            slot = slot + 1
        end

        while slot <= MaxEvents do
            AmagarCaixa(d, slot)
            slot = slot + 1
        end
    end

    -- Panells de la dreta: setmana vinent + totes les tasques pendents
    PosicionarPanells()
    PintarFiles('Prop', XPropera, AmpladaPanell, FilesPropera(), YPropera, AltPropera)
    PintarFiles('Tasca', XTasques, AmpladaPanell, FilesTasques(), YTasques, AltTasques)

    SKIN:Bang('!Redraw')
    return 1
end