from pathlib import Path

import pytest

from app.config import Config
from app.main import creer_app
from tests.client import Client

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def config(tmp_path):
    return Config(data=tmp_path / "data", scenarios=[RACINE / "scenarios", tmp_path / "data" / "scenarios"],
                  donnees=RACINE / "donnees", admins=("thibault",), ollama_defaut="http://127.0.0.1:9")


@pytest.fixture
def app(config):
    return creer_app(config)


def _client(app, user):
    return Client(app, {"Remote-User": user})


@pytest.fixture
def thibault(app):
    return _client(app, "thibault")


@pytest.fixture
def lea(app):
    return _client(app, "lea")


@pytest.fixture
def anonyme(app):
    return Client(app)
