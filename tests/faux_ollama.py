"""Un faux Ollama : répond à /api/tags avec la liste de modèles donnée."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FauxOllama:
    def __init__(self, modeles=("llama3.1:8b",)):
        self.modeles = list(modeles)
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/tags":
                    corps = json.dumps({"models": [{"name": m} for m in outer.modeles]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(corps)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *a):
                pass

        self.serveur = HTTPServer(("127.0.0.1", 0), H)
        self.adresse = f"http://127.0.0.1:{self.serveur.server_port}"
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)

    def __enter__(self):
        self.fil.start()
        return self

    def __exit__(self, *a):
        self.serveur.shutdown()
        self.serveur.server_close()
