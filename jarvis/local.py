"""Onde o senhor está, para o clima e o relógio: Caxias do Sul por padrão.

Uma consulta leve por IP (ipwho.is, HTTPS) a cada 30 min. O IP costuma errar a cidade por algumas dezenas de
quilômetros, então até `RAIO_CASA_KM` de casa vale Caxias do Sul; mais longe que isso, vale a cidade do IP (viagem).
Sem rede, fica o último local conhecido.
"""

import json
import math
import time
import urllib.request
from dataclasses import asdict, dataclass

from jarvis.config import dados

URL_IP = "https://ipwho.is/?fields=success,city,latitude,longitude,timezone"
INTERVALO_S = 1800
RAIO_CASA_KM = 150


@dataclass(frozen=True)
class Local:
    cidade: str
    latitude: float
    longitude: float
    fuso: str


CASA = Local("Caxias do Sul", -29.1678, -51.1794, "America/Sao_Paulo")


def distancia_km(a: Local, b: Local) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def por_ip(timeout: float = 5.0) -> Local | None:
    try:
        with urllib.request.urlopen(URL_IP, timeout=timeout) as resposta:
            d = json.load(resposta)
        if not d.get("success"):
            return None
        return Local(d["city"], float(d["latitude"]), float(d["longitude"]),
                     (d.get("timezone") or {}).get("id") or CASA.fuso)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def escolher(do_ip: Local | None) -> Local:
    if do_ip is None or distancia_km(do_ip, CASA) <= RAIO_CASA_KM:
        return CASA
    return do_ip


def _arquivo():
    return dados() / "local.json"


def atual(consultar=por_ip, agora: float | None = None) -> Local:
    agora = time.time() if agora is None else agora
    try:
        guardado = json.loads(_arquivo().read_text(encoding="utf-8"))
        anterior = Local(**guardado["local"])
        if agora - guardado["ts"] < INTERVALO_S:
            return anterior
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        anterior = None
    do_ip = consultar()
    if do_ip is None and anterior is not None:  # sem rede: fica onde estava
        local = anterior
    else:
        local = escolher(do_ip)
    _arquivo().write_text(json.dumps({"local": asdict(local), "ts": agora}, ensure_ascii=False), encoding="utf-8")
    return local
