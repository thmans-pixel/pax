"""Un faux Ollama : /api/tags (liste de modèles) et /api/chat en flux avec réponses programmées.

- `programmer(*reponses)` : les réponses (texte ou dict JSON) sont servies dans l'ordre, une par requête.
- `requetes` : les corps JSON reçus sur /api/chat (compteur : `len(requetes)`).
- `pause` : secondes entre deux morceaux (mode lent) ; `silence` : secondes avant le premier morceau.
- `eteindre()` : coupe le serveur (PC éteint).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FauxOllama:
    def __init__(self, modeles=("llama3.1:8b",), pause: float = 0.0, silence: float = 0.0, morceau: int = 40):
        self.modeles = list(modeles)
        self.reponses: list = []
        self.requetes: list[dict] = []
        self.pause, self.silence, self.morceau = pause, silence, morceau
        self.verrou = threading.Lock()
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

            def do_POST(self):
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                n = int(self.headers.get("Content-Length", 0))
                corps = json.loads(self.rfile.read(n))
                with outer.verrou:
                    outer.requetes.append(corps)
                    rep = outer.reponses.pop(0) if outer.reponses else None
                if rep is None:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "aucune réponse programmée"}).encode())
                    return
                texte = rep if isinstance(rep, str) else json.dumps(rep, ensure_ascii=False)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                try:
                    time.sleep(outer.silence)
                    for i in range(0, len(texte), outer.morceau):
                        ligne = {"model": corps.get("model"), "message": {"role": "assistant",
                                 "content": texte[i:i + outer.morceau]}, "done": False}
                        self.wfile.write((json.dumps(ligne) + "\n").encode())
                        self.wfile.flush()
                        time.sleep(outer.pause)
                    self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""},
                                                  "done": True}) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *a):
                pass

        ThreadingHTTPServer.daemon_threads = True
        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.adresse = f"http://127.0.0.1:{self.serveur.server_port}"
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        self.eteint = False

    def programmer(self, *reponses):
        with self.verrou:
            self.reponses.extend(reponses)

    def eteindre(self):
        if not self.eteint:
            self.eteint = True
            self.serveur.shutdown()
            self.serveur.server_close()

    def __enter__(self):
        self.fil.start()
        return self

    def __exit__(self, *a):
        self.eteindre()
