"""Generates the Power BI project (.pbip) of the dashboard.

Usage: python scripts/generar_pbip.py

Writes powerbi/Accidentes.pbip with its semantic model (model.bim) and its
report in PBIR format (one folder per page, one visual.json per visual), the
format of Power BI Desktop 2.159 (November 2026). Open Accidentes.pbip with Power BI Desktop and press
Actualizar to load the data.

The data source is chosen with the FuenteDatos parameter:
- Local: reads the parquet files of data/gold in this repository.
- Athena: queries the gold tables through the ODBC DSN set in DsnAthena.

Running this script again overwrites the changes made in Power BI Desktop,
so once the team edits the dashboard in Desktop, edit it there.
"""

import hashlib
import json
import pathlib
import shutil
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi"
NAME = "Accidentes"
GOLD_PATH = str(ROOT / "data" / "gold")
DSN = "accidentes-envigado"


# ---------------------------------------------------------------- semantic model

def m_string(text):
    """M text literal. M has no backslash escapes, only doubled quotes."""
    return '"' + text.replace('"', '""') + '"'


def m_lines(text):
    return text.strip("\n").split("\n")


def gold_query(athena_table, local_folder, select_and_types):
    """M query that reads one gold table from Athena or from local parquet."""
    return m_lines(f'''
let
    Datos = if FuenteDatos = "Athena"
        then Odbc.Query("dsn=" & DsnAthena, "SELECT * FROM {athena_table}")
        else LeerGold("{local_folder}"),
{select_and_types}''')


def types_step(columns, last_step="Tipos"):
    names = ", ".join(f'"{c}"' for c, _ in columns)
    types = ", ".join(f'{{"{c}", {t}}}' for c, t in columns)
    return f'''    Columnas = Table.SelectColumns(Datos, {{{names}}}),
    {last_step} = Table.TransformColumnTypes(Columnas, {{{types}}})'''


SINIESTROS_COLUMNS = [
    ("radicado", "type text"), ("fecha_hora", "type datetime"), ("fecha", "type date"),
    ("anio", "Int64.Type"), ("mes", "Int64.Type"), ("dia_semana", "type text"),
    ("hora", "Int64.Type"), ("franja", "type text"), ("clase_accidente", "type text"),
    ("causa", "type text"), ("barrio", "type text"), ("area", "type text"),
    ("registros", "Int64.Type"), ("lon", "type number"), ("lat", "type number"),
    ("gravedad", "type text"), ("con_victimas", "Int64.Type"),
]

SINIESTROS_M = gold_query("siniestros", "siniestros", types_step(SINIESTROS_COLUMNS) + ''',
    // Readable labels and a sort order for the categories
    Dias = [lunes = "Lunes", martes = "Martes", miercoles = "Miércoles", jueves = "Jueves",
            viernes = "Viernes", sabado = "Sábado", domingo = "Domingo"],
    OrdenDias = [lunes = 1, martes = 2, miercoles = 3, jueves = 4, viernes = 5, sabado = 6, domingo = 7],
    Franjas = [madrugada = "Madrugada", manana = "Mañana", tarde = "Tarde", noche = "Noche"],
    OrdenFranjas = [madrugada = 1, manana = 2, tarde = 3, noche = 4],
    Gravedades = [#"SOLO DAÑOS" = "Solo daños", HERIDOS = "Heridos", MUERTOS = "Muertos"],
    OrdenGravedades = [#"SOLO DAÑOS" = 1, HERIDOS = 2, MUERTOS = 3],
    ConDiaNum = Table.AddColumn(Tipos, "dia_num", each Record.FieldOrDefault(OrdenDias, [dia_semana], 8), Int64.Type),
    ConFranjaNum = Table.AddColumn(ConDiaNum, "franja_orden", each Record.FieldOrDefault(OrdenFranjas, [franja], 5), Int64.Type),
    ConGravedadNum = Table.AddColumn(ConFranjaNum, "gravedad_orden", each Record.FieldOrDefault(OrdenGravedades, [gravedad], 4), Int64.Type),
    Etiquetas = Table.TransformColumns(ConGravedadNum, {
        {"dia_semana", each Record.FieldOrDefault(Dias, _, _), type text},
        {"franja", each Record.FieldOrDefault(Franjas, _, _), type text},
        {"gravedad", each Record.FieldOrDefault(Gravedades, _, _), type text}
    })
in
    Etiquetas''')

PREDICCIONES_COLUMNS = [
    ("radicado", "type text"), ("fecha", "type date"), ("anio", "Int64.Type"),
    ("barrio", "type text"), ("con_victimas", "Int64.Type"), ("probabilidad", "type number"),
]
PREDICCIONES_M = gold_query("predicciones", "modelos\\predicciones",
                            types_step(PREDICCIONES_COLUMNS) + "\nin\n    Tipos")

METRICAS_COLUMNS = [
    ("modelo", "type text"), ("es_mejor", "Int64.Type"), ("roc_auc", "type number"),
    ("average_precision", "type number"), ("brier", "type number"),
    ("precision", "type number"), ("recall", "type number"),
    ("verdaderos_negativos", "Int64.Type"), ("falsos_positivos", "Int64.Type"),
    ("falsos_negativos", "Int64.Type"), ("verdaderos_positivos", "Int64.Type"),
    ("filas_entrenamiento", "Int64.Type"), ("filas_prueba", "Int64.Type"),
    ("prevalencia_prueba", "type number"),
]
METRICAS_M = gold_query("metricas", "modelos\\metricas", types_step(METRICAS_COLUMNS) + ''',
    Nombres = [regresion_logistica = "Regresión logística", gradient_boosting = "Gradient boosting"],
    Etiquetas = Table.TransformColumns(Tipos, {{"modelo", each Record.FieldOrDefault(Nombres, _, _), type text}})
in
    Etiquetas''')

MATRIZ_M = m_lines('''
let
    // Confusion matrix of the selected model, one row per cell
    Mejor = Table.SelectRows(metricas, each [es_mejor] = 1),
    Celdas = Table.AddColumn(Mejor, "celdas", each {
        [modelo = [modelo], real = "Con víctimas", predicho = "Con víctimas", casos = [verdaderos_positivos], orden_real = 1, orden_predicho = 1],
        [modelo = [modelo], real = "Con víctimas", predicho = "Solo daños", casos = [falsos_negativos], orden_real = 1, orden_predicho = 2],
        [modelo = [modelo], real = "Solo daños", predicho = "Con víctimas", casos = [falsos_positivos], orden_real = 2, orden_predicho = 1],
        [modelo = [modelo], real = "Solo daños", predicho = "Solo daños", casos = [verdaderos_negativos], orden_real = 2, orden_predicho = 2]
    }),
    Tabla = Table.FromRecords(List.Combine(Celdas[celdas]),
        type table [modelo = text, real = text, predicho = text, casos = Int64.Type,
                    orden_real = Int64.Type, orden_predicho = Int64.Type])
in
    Tabla''')

CALENDARIO_M = m_lines('''
let
    Inicio = #date(2010, 1, 1),
    Fin = #date(2022, 12, 31),
    Fechas = List.Dates(Inicio, Duration.Days(Fin - Inicio) + 1, #duration(1, 0, 0, 0)),
    Tabla = Table.FromList(Fechas, Splitter.SplitByNothing(), type table [Fecha = date]),
    ConAnio = Table.AddColumn(Tabla, "Año", each Date.Year([Fecha]), Int64.Type),
    ConMesNum = Table.AddColumn(ConAnio, "Mes num", each Date.Month([Fecha]), Int64.Type),
    Meses = {"Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"},
    ConMes = Table.AddColumn(ConMesNum, "Mes", each Meses{Date.Month([Fecha]) - 1}, type text),
    ConInicioMes = Table.AddColumn(ConMes, "Inicio de mes", each Date.StartOfMonth([Fecha]), type date)
in
    ConInicioMes''')

LEER_GOLD_M = m_lines(r'''
// Reads every parquet file under a folder of data/gold. Partition folders
// like anio=2015 become the anio column, as Athena does.
(carpeta as text) as table =>
let
    Archivos = Folder.Files(RutaGold & "\" & carpeta),
    Parquet = Table.SelectRows(Archivos, each Text.Lower([Extension]) = ".parquet"),
    ConTablas = Table.AddColumn(Parquet, "tabla", each
        let
            Particion = Text.BetweenDelimiters([Folder Path], "anio=", "\"),
            Contenido = Parquet.Document([Content])
        in
            if Particion <> "" and not List.Contains(Table.ColumnNames(Contenido), "anio")
            then Table.AddColumn(Contenido, "anio", each Particion)
            else Contenido),
    Combinado = Table.Combine(ConTablas[tabla])
in
    Combinado''')


def column(name, data_type, hidden=False, summarize="none", sort_by=None, fmt=None, **extra):
    c = {"name": name, "dataType": data_type, "sourceColumn": name, "summarizeBy": summarize}
    if hidden:
        c["isHidden"] = True
    if sort_by:
        c["sortByColumn"] = sort_by
    if fmt:
        c["formatString"] = fmt
    c.update(extra)
    return c


def measure(name, expression, fmt=None, folder=None):
    m = {"name": name, "expression": expression}
    if fmt:
        m["formatString"] = fmt
    if folder:
        m["displayFolder"] = folder
    return m


def table(name, columns, m_expression, measures=(), **extra):
    t = {
        "name": name,
        "columns": columns,
        "partitions": [{"name": name, "mode": "import",
                        "source": {"type": "m", "expression": m_expression}}],
    }
    if measures:
        t["measures"] = list(measures)
    t.update(extra)
    return t


PCT = "0.0%"
INT = "#,0"

TABLES = [
    table("siniestros", [
        column("radicado", "string"),
        column("fecha_hora", "dateTime"),
        column("fecha", "dateTime"),
        column("anio", "int64"),
        column("mes", "int64"),
        column("dia_semana", "string", sort_by="dia_num"),
        column("dia_num", "int64", hidden=True),
        column("hora", "int64"),
        column("franja", "string", sort_by="franja_orden"),
        column("franja_orden", "int64", hidden=True),
        column("clase_accidente", "string"),
        column("causa", "string"),
        column("barrio", "string"),
        column("area", "string"),
        column("registros", "int64"),
        column("lon", "double", dataCategory="Longitude"),
        column("lat", "double", dataCategory="Latitude"),
        column("gravedad", "string", sort_by="gravedad_orden"),
        column("gravedad_orden", "int64", hidden=True),
        column("con_victimas", "int64"),
    ], SINIESTROS_M, [
        measure("Total siniestros", "COUNTROWS(siniestros)", INT),
        measure("Con víctimas", "SUM(siniestros[con_victimas])", INT),
        measure("% con víctimas", "DIVIDE([Con víctimas], [Total siniestros])", PCT),
        measure("Con muertos",
                'CALCULATE([Total siniestros], KEEPFILTERS(siniestros[gravedad] = "Muertos"))', INT),
        measure("Con heridos",
                'CALCULATE([Total siniestros], KEEPFILTERS(siniestros[gravedad] = "Heridos"))', INT),
        measure("Solo daños",
                'CALCULATE([Total siniestros], KEEPFILTERS(siniestros[gravedad] = "Solo daños"))', INT),
        measure("Siniestros año anterior",
                "CALCULATE([Total siniestros], SAMEPERIODLASTYEAR(Calendario[Fecha]))", INT),
        measure("Variación anual",
                "DIVIDE([Total siniestros] - [Siniestros año anterior], [Siniestros año anterior])", PCT),
    ]),
    table("predicciones", [
        column("radicado", "string", hidden=True),
        column("fecha", "dateTime"),
        column("anio", "int64"),
        column("barrio", "string"),
        column("con_victimas", "int64"),
        column("probabilidad", "double", fmt=PCT),
    ], PREDICCIONES_M, [
        measure("Siniestros evaluados", "COUNTROWS(predicciones)", INT),
        measure("Probabilidad media", "AVERAGE(predicciones[probabilidad])", PCT),
        measure("Tasa real de víctimas", "AVERAGE(predicciones[con_victimas])", PCT),
    ]),
    table("metricas", [
        column("modelo", "string"),
        column("es_mejor", "int64"),
        column("roc_auc", "double", fmt="0.000"),
        column("average_precision", "double", fmt="0.000"),
        column("brier", "double", fmt="0.000"),
        column("precision", "double", fmt=PCT),
        column("recall", "double", fmt=PCT),
        column("verdaderos_negativos", "int64", fmt=INT),
        column("falsos_positivos", "int64", fmt=INT),
        column("falsos_negativos", "int64", fmt=INT),
        column("verdaderos_positivos", "int64", fmt=INT),
        column("filas_entrenamiento", "int64", fmt=INT),
        column("filas_prueba", "int64", fmt=INT),
        column("prevalencia_prueba", "double", fmt=PCT),
    ], METRICAS_M, [
        measure("Mejor modelo", "CALCULATE(MAX(metricas[modelo]), metricas[es_mejor] = 1)"),
        measure("ROC AUC mejor modelo", "CALCULATE(MAX(metricas[roc_auc]), metricas[es_mejor] = 1)", "0.000"),
        measure("Precisión mejor modelo", "CALCULATE(MAX(metricas[precision]), metricas[es_mejor] = 1)", PCT),
        measure("Recall mejor modelo", "CALCULATE(MAX(metricas[recall]), metricas[es_mejor] = 1)", PCT),
    ]),
    table("matriz_confusion", [
        column("modelo", "string"),
        column("real", "string", sort_by="orden_real"),
        column("predicho", "string", sort_by="orden_predicho"),
        column("casos", "int64", fmt=INT),
        column("orden_real", "int64", hidden=True),
        column("orden_predicho", "int64", hidden=True),
    ], MATRIZ_M, [
        measure("Total casos", "SUM(matriz_confusion[casos])", INT),
    ]),
    table("Calendario", [
        column("Fecha", "dateTime", isKey=True),
        column("Año", "int64"),
        column("Mes num", "int64", hidden=True),
        column("Mes", "string", sort_by="Mes num"),
        column("Inicio de mes", "dateTime"),
    ], CALENDARIO_M, dataCategory="Time"),
]

RELATIONSHIPS = [
    {"name": "siniestros_calendario", "fromTable": "siniestros", "fromColumn": "fecha",
     "toTable": "Calendario", "toColumn": "Fecha"},
    {"name": "predicciones_siniestros", "fromTable": "predicciones", "fromColumn": "radicado",
     "toTable": "siniestros", "toColumn": "radicado"},
]

EXPRESSIONS = [
    {"name": "FuenteDatos", "kind": "m",
     "expression": '"Local" meta [IsParameterQuery=true, List={"Local", "Athena"}, '
                   'DefaultValue="Local", Type="Text", IsParameterQueryRequired=true]',
     "annotations": [{"name": "PBI_ResultType", "value": "Text"}]},
    {"name": "RutaGold", "kind": "m",
     "expression": m_string(GOLD_PATH) +
                   ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
     "annotations": [{"name": "PBI_ResultType", "value": "Text"}]},
    {"name": "DsnAthena", "kind": "m",
     "expression": m_string(DSN) +
                   ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
     "annotations": [{"name": "PBI_ResultType", "value": "Text"}]},
    {"name": "LeerGold", "kind": "m", "expression": LEER_GOLD_M,
     "annotations": [{"name": "PBI_ResultType", "value": "Function"}]},
]

MODEL = {
    "compatibilityLevel": 1567,
    "model": {
        "culture": "es-CO",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "es-CO",
        "tables": TABLES,
        "relationships": RELATIONSHIPS,
        "expressions": EXPRESSIONS,
        "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}],
    },
}


# ---------------------------------------------------------------- report (PBIR)

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
THEME = "Fluent2-CY26SU10"
# The base theme is kept inside the report itself; Desktop ships it in
# bin/WebView2Resources/minerva/sharedresources/BaseThemes if it is ever lost
THEME_PATH = pathlib.Path("StaticResources") / "SharedResources" / "BaseThemes" / f"{THEME}.json"

# Aliases used inside filter queries
ALIAS = {"siniestros": "s", "predicciones": "p", "metricas": "m",
         "matriz_confusion": "mc", "Calendario": "c"}


def C(entity, prop):
    return ("Column", entity, prop)


def M(entity, prop):
    return ("Measure", entity, prop)


def ref(field, alias=False):
    kind, entity, prop = field
    source = {"Source": ALIAS[entity]} if alias else {"Entity": entity}
    return {kind: {"Expression": {"SourceRef": source}, "Property": prop}}


def qref(field):
    return f"{field[1]}.{field[2]}"


def lit(value):
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = f"{value}L"
    elif isinstance(value, float):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def visual_id(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:20]


def top_n_filter(category, by_measure, n):
    entity = category[1]
    alias = ALIAS[entity]
    return {
        "name": visual_id("topn", qref(category), n),
        "field": ref(category),
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {"Name": "subquery", "Type": 2, "Expression": {"Subquery": {"Query": {
                    "Version": 2,
                    "From": [{"Name": alias, "Entity": entity, "Type": 0}],
                    "Select": [{**ref(category, alias=True), "Name": "field"}],
                    "OrderBy": [{"Direction": 2, "Expression": ref(by_measure, alias=True)}],
                    "Top": n,
                }}}},
                {"Name": alias, "Entity": entity, "Type": 0},
            ],
            "Where": [{"Condition": {"In": {
                "Expressions": [ref(category, alias=True)],
                "Table": {"SourceRef": {"Source": "subquery"}},
            }}}],
        },
    }


class Page:
    def __init__(self, name, title, subtitle):
        self.name = name
        self.id = visual_id("page", name)
        self.visuals = []
        self.textbox(24, 12, 470, 64, title, subtitle)

    def add(self, vtype, x, y, w, h, roles=None, title=None, order_by=None,
            objects=None, filters=None, sync_group=None):
        z = len(self.visuals) * 1000
        visual = {"visualType": vtype}
        if roles:
            state = {}
            for role, fields in roles.items():
                projections = []
                for f in fields:
                    p = {"field": ref(f), "queryRef": qref(f), "nativeQueryRef": f[2]}
                    if vtype == "slicer":
                        p["active"] = True
                    projections.append(p)
                state[role] = {"projections": projections}
            visual["query"] = {"queryState": state}
            if order_by:
                visual["query"]["sortDefinition"] = {
                    "sort": [{"field": ref(f), "direction": "Descending" if d == 2 else "Ascending"}
                             for f, d in order_by],
                    "isDefaultSort": False,
                }
        if objects:
            visual["objects"] = objects
        if title:
            visual["visualContainerObjects"] = {"title": [{"properties": {
                "show": lit(True), "text": lit(title)}}]}
        if sync_group:
            visual["syncGroup"] = {"groupName": sync_group,
                                   "fieldChanges": True, "filterChanges": True}
        visual["drillFilterOtherVisuals"] = True
        container = {
            "$schema": f"{SCHEMA}/visualContainer/2.14.0/schema.json",
            "name": visual_id(self.name, vtype, x, y),
            "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
            "visual": visual,
        }
        if filters:
            container["filterConfig"] = {"filters": filters}
        self.visuals.append(container)

    def textbox(self, x, y, w, h, title, subtitle):
        paragraphs = [{"textRuns": [{"value": title, "textStyle": {
            "fontWeight": "bold", "fontSize": "18pt"}}]}]
        if subtitle:
            paragraphs.append({"textRuns": [{"value": subtitle, "textStyle": {
                "fontSize": "10pt", "color": "#605E5C"}}]})
        self.add("textbox", x, y, w, h,
                 objects={"general": [{"properties": {"paragraphs": paragraphs}}]})

    def card(self, x, y, w, h, field):
        self.add("card", x, y, w, h, {"Values": [field]})

    def slicers(self):
        fields = [C("Calendario", "Año"), C("siniestros", "barrio"),
                  C("siniestros", "clase_accidente"), C("siniestros", "gravedad")]
        for i, f in enumerate(fields):
            self.add("slicer", 510 + i * 188, 16, 178, 58, {"Values": [f]},
                     objects={"data": [{"properties": {"mode": lit("Dropdown")}}]},
                     sync_group=qref(f))

    def page_json(self):
        return {
            "$schema": f"{SCHEMA}/page/2.1.0/schema.json",
            "name": self.id,
            "displayName": self.name,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        }


def heat_rule(measure_field, color):
    return {"values": [{
        "properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
            "Input": ref(measure_field),
            "FillRule": {"linearGradient2": {
                "min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}},
                "max": {"color": {"Literal": {"Value": f"'{color}'"}}},
                "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}},
            }},
        }}}}}},
        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                     "metadata": qref(measure_field)},
    }]}


def build_pages():
    s_total = M("siniestros", "Total siniestros")
    s_victimas = M("siniestros", "Con víctimas")
    s_pct = M("siniestros", "% con víctimas")
    s_muertos = M("siniestros", "Con muertos")
    barrio = C("siniestros", "barrio")
    causa = C("siniestros", "causa")
    pages = []

    p = Page("Resumen", "Siniestros viales en Envigado",
             "2010 a junio de 2022. Un siniestro es un radicado con su gravedad más alta.")
    p.slicers()
    for i, f in enumerate([s_total, s_victimas, s_pct, s_muertos]):
        p.card(24 + i * 312, 92, 296, 110, f)
    p.add("lineChart", 24, 218, 760, 482,
          {"Category": [C("Calendario", "Inicio de mes")], "Y": [s_total, s_victimas]},
          title="Siniestros por mes")
    p.add("hundredPercentStackedColumnChart", 800, 218, 456, 482,
          {"Category": [C("Calendario", "Año")], "Series": [C("siniestros", "gravedad")],
           "Y": [s_total]},
          title="Composición de la gravedad por año")
    pages.append(p)

    p = Page("Cuándo", "Cuándo ocurren",
             "Día de la semana, hora y franja del día.")
    p.slicers()
    p.add("pivotTable", 24, 92, 1232, 330,
          {"Rows": [C("siniestros", "dia_semana")], "Columns": [C("siniestros", "hora")],
           "Values": [s_total]},
          title="Siniestros por día y hora", objects=heat_rule(s_total, "#C0392B"))
    p.add("lineClusteredColumnComboChart", 24, 438, 760, 262,
          {"Category": [C("siniestros", "hora")], "Y": [s_total], "Y2": [s_pct]},
          title="Siniestros y proporción con víctimas por hora")
    p.add("clusteredColumnChart", 800, 438, 456, 262,
          {"Category": [C("siniestros", "franja")], "Y": [s_pct]},
          title="Proporción con víctimas por franja")
    pages.append(p)

    p = Page("Dónde y por qué", "Dónde y por qué",
             "Barrios, clases de accidente y causas más frecuentes.")
    p.slicers()
    p.add("clusteredBarChart", 24, 92, 600, 608, {"Category": [barrio], "Y": [s_total]},
          title="15 barrios con más siniestros", order_by=[(s_total, 2)],
          filters=[top_n_filter(barrio, s_total, 15)])
    p.add("clusteredBarChart", 640, 92, 616, 250,
          {"Category": [C("siniestros", "clase_accidente")], "Y": [s_total, s_victimas]},
          title="Clase de accidente", order_by=[(s_total, 2)])
    p.add("clusteredBarChart", 640, 358, 616, 342, {"Category": [causa], "Y": [s_total]},
          title="10 causas más frecuentes", order_by=[(s_total, 2)],
          filters=[top_n_filter(causa, s_total, 10)])
    pages.append(p)

    p = Page("Modelo", "Modelo de víctimas",
             "Probabilidad de que un siniestro deje víctimas. Entrenado con 2010-2019, "
             "evaluado con 2020-2022, umbral 0.5.")
    model_cards = [M("metricas", "Mejor modelo"), M("metricas", "ROC AUC mejor modelo"),
                   M("metricas", "Precisión mejor modelo"), M("metricas", "Recall mejor modelo")]
    for i, f in enumerate(model_cards):
        p.card(24 + i * 312, 92, 296, 110, f)
    p.add("tableEx", 24, 218, 620, 200,
          {"Values": [C("metricas", c) for c in
                      ["modelo", "roc_auc", "average_precision", "brier", "precision", "recall"]]},
          title="Comparación de modelos")
    p.add("pivotTable", 660, 218, 596, 200,
          {"Rows": [C("matriz_confusion", "real")],
           "Columns": [C("matriz_confusion", "predicho")],
           "Values": [M("matriz_confusion", "Total casos")]},
          title="Matriz de confusión del mejor modelo (filas: real)",
          objects=heat_rule(M("matriz_confusion", "Total casos"), "#2E86C1"))
    pbarrio = C("predicciones", "barrio")
    p.add("clusteredColumnChart", 24, 434, 1232, 266,
          {"Category": [pbarrio],
           "Y": [M("predicciones", "Probabilidad media"), M("predicciones", "Tasa real de víctimas")]},
          title="Probabilidad predicha y tasa real de víctimas, 15 barrios con más casos de prueba",
          order_by=[(M("predicciones", "Siniestros evaluados"), 2)],
          filters=[top_n_filter(pbarrio, M("predicciones", "Siniestros evaluados"), 15)])
    pages.append(p)
    return pages




# ---------------------------------------------------------------- files

def platform(kind):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind, "displayName": NAME},
        "config": {"version": "2.0",
                   "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"accidentes-envigado/{kind}"))},
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(report_dir):
    theme = (report_dir / THEME_PATH).read_bytes()
    # Start clean so pages or visuals removed here do not linger on disk
    if report_dir.exists():
        shutil.rmtree(report_dir)
    write_json(report_dir / ".platform", platform("Report"))
    write_json(report_dir / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })
    definition = report_dir / "definition"
    write_json(definition / "version.json", {
        "$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    write_json(definition / "report.json", {
        "$schema": f"{SCHEMA}/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {
            "name": THEME,
            "reportVersionAtImport": {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"},
            "type": "SharedResources",
        }},
        "resourcePackages": [{
            "name": "SharedResources",
            "type": "SharedResources",
            "items": [{"name": THEME, "path": f"BaseThemes/{THEME}.json", "type": "BaseTheme"}],
        }],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
        },
    })
    theme_out = report_dir / THEME_PATH
    theme_out.parent.mkdir(parents=True, exist_ok=True)
    theme_out.write_bytes(theme)

    pages = build_pages()
    write_json(definition / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
        "pageOrder": [p.id for p in pages],
        "activePageName": pages[0].id,
    })
    for page in pages:
        page_dir = definition / "pages" / page.id
        write_json(page_dir / "page.json", page.page_json())
        for visual in page.visuals:
            write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)
    return pages


def main():
    model_dir = OUT / f"{NAME}.SemanticModel"
    report_dir = OUT / f"{NAME}.Report"
    write_json(OUT / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    write_json(model_dir / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {},
    })
    write_json(model_dir / "model.bim", MODEL)
    write_json(model_dir / ".platform", platform("SemanticModel"))
    pages = write_report(report_dir)
    visuals = sum(len(p.visuals) for p in pages)
    print(f"Wrote {OUT / (NAME + '.pbip')}: {len(pages)} pages, {visuals} visuals")
    print(f"Local data source: {GOLD_PATH}")


if __name__ == "__main__":
    main()
