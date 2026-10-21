import json

from jarvis import consultas, local

GRAMADO = local.Local("Gramado", -29.37, -50.87, "America/Sao_Paulo")  # ~40 km de Caxias
LISBOA = local.Local("Lisboa", 38.72, -9.14, "Europe/Lisbon")


def test_perto_de_casa_vale_caxias_longe_vale_o_ip():
    assert local.escolher(GRAMADO) == local.CASA  # o IP erra a cidade por dezenas de km
    assert local.escolher(LISBOA) == LISBOA
    assert local.escolher(None) == local.CASA
    assert 30 < local.distancia_km(GRAMADO, local.CASA) < 60


def test_consulta_o_ip_no_maximo_a_cada_30_min(dados_tmp):
    chamadas = []

    def ip():
        chamadas.append(1)
        return LISBOA
    assert local.atual(ip, agora=1000.0) == LISBOA
    assert local.atual(ip, agora=1000.0 + local.INTERVALO_S - 1) == LISBOA
    assert len(chamadas) == 1
    local.atual(ip, agora=1000.0 + local.INTERVALO_S + 1)
    assert len(chamadas) == 2


def test_sem_rede_fica_o_ultimo_local(dados_tmp):
    local.atual(lambda: LISBOA, agora=0.0)
    assert local.atual(lambda: None, agora=local.INTERVALO_S + 1) == LISBOA
    (dados_tmp / "local.json").unlink()
    assert local.atual(lambda: None, agora=0.0) == local.CASA


def test_le_a_resposta_do_ipwho(monkeypatch):
    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return json.dumps({"success": True, "city": "Lisboa", "latitude": 38.72, "longitude": -9.14,
                               "timezone": {"id": "Europe/Lisbon"}}).encode()
    monkeypatch.setattr(local.urllib.request, "urlopen", lambda url, timeout: Resposta())
    assert local.por_ip() == LISBOA
    monkeypatch.setattr(local.urllib.request, "urlopen", lambda url, timeout: (_ for _ in ()).throw(OSError()))
    assert local.por_ip() is None


def test_url_do_clima_usa_as_coordenadas_e_o_fuso_do_lugar():
    url = consultas.URL_CLIMA.format(latitude=-29.1678, longitude=-51.1794)
    assert "latitude=-29.1678&longitude=-51.1794" in url and "timezone=auto" in url
