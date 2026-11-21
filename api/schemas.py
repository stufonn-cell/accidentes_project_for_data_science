"""Request and response bodies of the API. Field names are in Spanish, like the data."""

import re
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_BATCH = 100

# Short printable text: no control characters, at most 120 characters
Texto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120,
                      pattern=r"^[^\x00-\x1f\x7f]+$"),
]
# Same format as FECHA_ACCIDENTE in the RUNT source: MM/AAAA
FECHA = re.compile(r"^(0[1-9]|1[0-2])/(\d{4})$")
MIN_YEAR, MAX_YEAR = 2000, 2100
# src/silver.py marks model years before 1950 as impossible
MIN_MODEL_YEAR = 1950


class Vehiculo(BaseModel):
    """A vehicle involved in an accident with victims, as the RUNT reports it."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "tipo": "MOTOCICLETA",
        "marca": "AKT",
        "modelo": 2023,
        "fecha": "06/2024",
        "departamento": "ANTIOQUIA",
        "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE",
    }})

    tipo: Texto = Field(description="Tipo de vehiculo, por ejemplo MOTOCICLETA o AUTOMOVIL.")
    marca: Optional[Texto] = Field(
        default=None, description="Marca. Las poco frecuentes o vacias se agrupan en OTRAS.")
    modelo: Optional[int] = Field(
        default=None, ge=MIN_MODEL_YEAR, le=MAX_YEAR + 1,
        description="Año modelo del vehiculo. Si falta, el modelo lo trata como desconocido.")
    fecha: Optional[str] = Field(
        default=None, description="Mes del siniestro en formato MM/AAAA, como en el RUNT. "
                                  "Alternativa: anio y mes.")
    anio: Optional[int] = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR,
                                description="Año del siniestro, si no se envia fecha.")
    mes: Optional[int] = Field(default=None, ge=1, le=12,
                               description="Mes del siniestro (1 a 12), si no se envia fecha.")
    departamento: Texto = Field(description="Departamento del siniestro.")
    autoridad: Texto = Field(description="Autoridad de transito que reporta.")
    identificador: Optional[Annotated[str, StringConstraints(
        strip_whitespace=True, max_length=40, pattern=r"^[A-Za-z0-9._-]*$")]] = Field(
        default=None, description="Identificador opcional. Se devuelve tal cual en la respuesta.")

    @model_validator(mode="after")
    def date_and_model_year(self):
        if self.fecha is not None:
            match = FECHA.match(self.fecha.strip())
            if match is None:
                raise ValueError("fecha debe tener el formato MM/AAAA")
            month, year = int(match.group(1)), int(match.group(2))
            if not MIN_YEAR <= year <= MAX_YEAR:
                raise ValueError(f"el año de fecha debe estar entre {MIN_YEAR} y {MAX_YEAR}")
            if (self.anio, self.mes) not in ((None, None), (year, month)):
                raise ValueError("fecha no coincide con anio y mes")
            self.anio, self.mes = year, month
        if self.anio is None or self.mes is None:
            raise ValueError("falta la fecha: envie fecha (MM/AAAA) o anio y mes")
        # Same rule as modelo_invalido in src/silver.py
        if self.modelo is not None and self.modelo > self.anio + 1:
            raise ValueError("el modelo no puede ser posterior al año del siniestro + 1")
        return self


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehiculos: list[Vehiculo] = Field(min_length=1, max_length=MAX_BATCH)


class Prediccion(BaseModel):
    identificador: Optional[str] = None
    probabilidad: float = Field(
        ge=0, le=1, description="Probabilidad de que el siniestro con victimas tenga muertos.")
    alerta: bool = Field(description="Verdadero si la probabilidad alcanza el umbral de decision.")
    entrada_modelo: dict[str, Optional[float | str]] = Field(
        description="Variables con las que se consulto el modelo, ya derivadas y agrupadas.")
    categorias_agrupadas: list[str] = Field(
        description="Variables cuyo valor se llevo a OTRO u OTRAS por ser raro o nuevo.")
    categorias_desconocidas: list[str] = Field(
        description="Variables cuyo valor el modelo no vio en el entrenamiento.")


class RespuestaPrediccion(Prediccion):
    umbral_decision: float
    modelo: str
    version: str


class RespuestaLote(BaseModel):
    modelo: str
    version: str
    umbral_decision: float
    total: int
    predicciones: list[Prediccion]


class Variables(BaseModel):
    categoricas: list[str]
    numericas: list[str]


class Salud(BaseModel):
    estado: str
    modelo: str
    version: str
    sha256: str
    objetivo: str
    umbral_decision: float
    variables: Variables
    origen: str
    requiere_api_key: bool
