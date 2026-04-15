"""
KHEDIM AI GENERATE VIDEO — Backend Flask v13.0
TPU v5 / v6e Trillium Edition — par KHEDIM BENYAKHLEF

Déployé sur Render.com (render.yaml inclus)
Se connecte au notebook TPU via URL ngrok

NOTES SÉCURITÉ :
  - Aucune clé Anthropic requise (détection style par mots-clés)
  - PIN hashé SHA-256 — jamais stocké en clair
  - Authentification par token JWT léger (pas de session)
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests, os, uuid, time, logging, threading, hashlib, secrets
from queue import Queue, Empty
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "outputs")
LOG_DIR    = os.path.join(BASE_DIR, "..", "logs")
FRONT_DIR  = os.path.join(BASE_DIR, "..", "frontend")
for d in [OUTPUT_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "server.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("KhedimAI")

# ════════════════════════════════════════════════════════════════════════════
#  AUTH — PIN hash + token de session
#  Le PIN par défaut est "2022002" mais peut être changé via ACCESS_PIN
#  L'auth Anthropic API est DÉSACTIVÉE — détection style par mots-clés
# ════════════════════════════════════════════════════════════════════════════
_RAW_PIN        = os.getenv("ACCESS_PIN", "2022002")
ACCESS_PIN_HASH = hashlib.sha256(_RAW_PIN.encode()).hexdigest()

# Tokens de session valides (en mémoire, durée de vie 24h)
_sessions: dict[str, float] = {}
_slock = threading.Lock()

SESSION_TTL = 86400  # 24 heures

def check_pin(pin: str) -> bool:
    """Vérifie le PIN sans timing attack."""
    return secrets.compare_digest(
        hashlib.sha256(str(pin).encode()).hexdigest(),
        ACCESS_PIN_HASH,
    )

def create_session() -> str:
    """Génère un token de session sécurisé."""
    token = secrets.token_urlsafe(32)
    with _slock:
        _sessions[token] = time.time() + SESSION_TTL
    return token

def valid_session(token: str) -> bool:
    """Vérifie qu'un token de session est valide et non expiré."""
    with _slock:
        exp = _sessions.get(token)
    return exp is not None and time.time() < exp

def require_auth(f):
    """Décorateur — rejette les requêtes sans session valide."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Session-Token", "")
        if not token or not valid_session(token):
            return jsonify({"error": "Non authentifié", "code": 401}), 401
        return f(*args, **kwargs)
    return wrapper

# ── TPU URL ───────────────────────────────────────────────────────────────
_tpu_url = {"url": os.getenv("TPU_URL", "NOT_CONFIGURED")}

def get_url(): return _tpu_url["url"]
def set_url(u): _tpu_url["url"] = u; os.environ["TPU_URL"] = u

HEADERS = {
    "ngrok-skip-browser-warning": "true",
    "Content-Type": "application/json",
}

# ── Job Queue ─────────────────────────────────────────────────────────────
job_queue  = Queue(maxsize=10)
job_status = {}
_jlock     = threading.Lock()

# ════════════════════════════════════════════════════════════════════════════
#  POLL — attend la fin du job TPU
# ════════════════════════════════════════════════════════════════════════════
def poll_until_done(url, job_id, timeout=3600):
    prog_url = url.rstrip("/") + "/progress"
    fails    = 0
    deadline = time.time() + timeout
    sleep_t  = 5

    while time.time() < deadline:
        time.sleep(sleep_t)

        with _jlock:
            if job_status.get(job_id, {}).get("status") == "cancelled":
                return False, "Annulé par l'utilisateur"

        try:
            r  = requests.get(prog_url, timeout=15, headers=HEADERS)
            ct = r.headers.get("Content-Type", "")
            if "html" in ct.lower():
                continue

            if r.status_code == 200:
                d   = r.json()
                pct = int(d.get("progress", 0))
                with _jlock:
                    if job_id in job_status:
                        job_status[job_id].update({
                            "progress":      pct,
                            "current_frame": d.get("current_frame", 0),
                            "total_frames":  d.get("total_frames", 0),
                            "step":          d.get("step", "En cours..."),
                            "device":        d.get("device", ""),
                            "quality":       d.get("quality", ""),
                        })
                fails   = 0
                sleep_t = 5

                if d.get("error"):
                    return False, d["error"]

                if not d.get("running", True) and pct >= 100:
                    fp = d.get("final_path") or d.get("video_path") or d.get("image_path")
                    if fp:
                        fname  = os.path.basename(fp)
                        prefix = "/image/" if (d.get("image_path") and not d.get("video_path")) else "/final/"
                        return True, url.rstrip("/") + prefix + fname
                    return False, "Fichier résultat introuvable"
            else:
                fails += 1

        except Exception as e:
            fails   += 1
            sleep_t  = min(sleep_t + 5, 30)
            log.warning(f"[POLL {job_id}] {e} ({fails})")

        if fails >= 15:
            return False, "TPU injoignable après 15 tentatives"

    return False, "Timeout dépassé (>1h)"


def send_async(job_id, endpoint, payload):
    url = get_url()
    if not url.startswith("http"):
        return False, "URL TPU non configurée — entrez l'URL ngrok dans les paramètres"

    try:
        log.info(f"[{job_id}] POST {url[:50]}{endpoint}")
        with _jlock:
            if job_id in job_status:
                job_status[job_id].update({"progress": 2, "step": "Connexion TPU..."})

        resp = requests.post(
            url.rstrip("/") + endpoint,
            json=payload, headers=HEADERS, timeout=30,
        )
        resp.raise_for_status()
        if "html" in resp.headers.get("Content-Type", "").lower():
            raise ValueError("Réponse HTML reçue (ngrok browser warning — ignorez-la)")

        data = resp.json()
        if data.get("error"):
            return False, data["error"]

        if data.get("status") in ("queued", "processing", "ok") or data.get("job_id"):
            with _jlock:
                if job_id in job_status:
                    job_status[job_id].update({
                        "step":    "🔥 Génération TPU...",
                        "progress": 5,
                        "device":  data.get("device", ""),
                        "quality": data.get("quality", ""),
                    })

            def _poll():
                ok, result = poll_until_done(url, job_id)
                with _jlock:
                    if ok:
                        job_status[job_id].update({
                            "status": "done", "result": result,
                            "progress": 100, "step": "✅ Terminé!"
                        })
                    else:
                        job_status[job_id].update({
                            "status": "error", "error": result, "step": "❌ Erreur"
                        })

            threading.Thread(target=_poll, daemon=True).start()
            return True, "polling"

        for key in ("final_url", "video_url", "image_url"):
            if data.get(key):
                return True, data[key]

        return False, f"Réponse inattendue: {str(data)[:80]}"

    except Exception as e:
        return False, str(e)[:150]


# ── Worker ────────────────────────────────────────────────────────────────
def worker():
    while True:
        try:
            job = job_queue.get(timeout=5)
        except Empty:
            continue
        if job is None:
            break

        jid = job["job_id"]
        with _jlock:
            job_status[jid].update({"status": "processing", "step": "Démarrage..."})

        jtype = job.get("type", "video")
        log.info(f"[WORKER] {jtype} | {jid}")

        try:
            if jtype == "video":
                payload = {
                    "prompt":         job["prompt"],
                    "style":          job.get("style"),
                    "duration_sec":   job.get("duration_sec", 5),
                    "steps":          job.get("steps", 35),
                    "guidance":       job.get("guidance", 7.5),
                    "fps":            job.get("fps", 8),
                    "seed":           job.get("seed", -1),
                    "voix_active":    job.get("voix_active", True),
                    "style_voix":     job.get("style_voix", "masculin"),
                    "texte_voix":     job.get("texte_voix"),
                    "musique_active": job.get("musique_active", True),
                }
                ok, result = send_async(jid, "/generate", payload)

            elif jtype == "image":
                payload = {
                    "prompt":     job["prompt"],
                    "style":      job.get("style"),
                    "resolution": job.get("resolution", "1024x1024"),
                    "steps":      job.get("steps", 35),
                    "guidance":   job.get("guidance", 7.5),
                    "seed":       job.get("seed", -1),
                }
                ok, result = send_async(jid, "/generate_image", payload)
            else:
                ok, result = False, f"Type inconnu: {jtype}"

            if not ok:
                with _jlock:
                    job_status[jid].update({
                        "status": "error", "error": result, "step": "❌ Erreur"
                    })
            elif result != "polling":
                with _jlock:
                    job_status[jid].update({
                        "status": "done", "result": result,
                        "progress": 100, "step": "✅ Terminé!"
                    })

        except Exception as e:
            log.exception(f"[WORKER] {jid}")
            with _jlock:
                job_status[jid].update({
                    "status": "error", "error": str(e), "step": "❌ Exception"
                })
        finally:
            job_queue.task_done()


_worker = threading.Thread(target=worker, daemon=True, name="KhedimAI-Worker")
_worker.start()


# ════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════════════════════════════════

# ── Statique ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONT_DIR, "index.html")

@app.route("/<path:p>")
def static_files(p):
    return send_from_directory(FRONT_DIR, p)

# ── Auth ──────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    """
    Body: { "pin": "2022002" }
    Retourne: { "token": "...", "ok": true }

    Le PIN est vérifié en temps constant (résistant aux timing attacks).
    Aucune clé Anthropic n'est requise.
    """
    d   = request.get_json(force=True) or {}
    pin = str(d.get("pin", "")).strip()

    if not pin:
        return jsonify({"error": "PIN manquant"}), 400

    if not check_pin(pin):
        log.warning(f"PIN incorrect depuis {request.remote_addr}")
        time.sleep(1)  # Anti-brute-force
        return jsonify({"error": "PIN incorrect"}), 401

    token = create_session()
    log.info(f"Connexion réussie depuis {request.remote_addr}")
    return jsonify({"ok": True, "token": token})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = request.headers.get("X-Session-Token", "")
    with _slock:
        _sessions.pop(token, None)
    return jsonify({"ok": True})

# ── Config TPU URL ────────────────────────────────────────────────────────
@app.route("/api/config", methods=["POST"])
@require_auth
def api_config():
    d   = request.get_json(force=True) or {}
    url = d.get("tpu_url", "").strip()
    if url:
        set_url(url)
        log.info(f"TPU URL mise à jour: {url[:50]}")
    return jsonify({"ok": True, "tpu_url": get_url()})

@app.route("/api/config", methods=["GET"])
@require_auth
def api_config_get():
    return jsonify({"tpu_url": get_url()})

# ── Health ────────────────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    tpu_ok  = False
    tpu_inf = {}
    url     = get_url()
    if url.startswith("http"):
        try:
            r = requests.get(url.rstrip("/") + "/health", timeout=5, headers=HEADERS)
            if r.status_code == 200 and "html" not in r.headers.get("Content-Type",""):
                tpu_ok  = True
                tpu_inf = r.json()
        except Exception:
            pass
    return jsonify({
        "ok":      True,
        "version": "13.0-tpu5",
        "tpu_url": url,
        "tpu_ok":  tpu_ok,
        "tpu":     tpu_inf,
        "jobs":    len(job_status),
        "queue":   job_queue.qsize(),
        "time":    datetime.now(timezone.utc).isoformat(),
    })

# ── Génération vidéo ──────────────────────────────────────────────────────
@app.route("/api/generate", methods=["POST"])
@require_auth
def api_generate():
    d      = request.get_json(force=True) or {}
    prompt = d.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt vide"}), 400

    jid = uuid.uuid4().hex[:10]
    job = {
        "job_id":         jid,
        "type":           "video",
        "prompt":         prompt,
        "style":          d.get("style"),
        "duration_sec":   min(int(d.get("duration_sec", 5)), 600),
        "steps":          min(int(d.get("steps", 35)), 60),
        "guidance":       float(d.get("guidance", 7.5)),
        "fps":            int(d.get("fps", 8)),
        "seed":           int(d.get("seed", -1)),
        "voix_active":    bool(d.get("voix_active", True)),
        "style_voix":     d.get("style_voix", "masculin"),
        "texte_voix":     d.get("texte_voix"),
        "musique_active": bool(d.get("musique_active", True)),
    }

    with _jlock:
        job_status[jid] = {
            "status": "queued", "progress": 0, "step": "En attente...",
            "result": None, "error": None, "type": "video",
            "created": datetime.now(timezone.utc).isoformat(),
        }

    if job_queue.full():
        return jsonify({"error": "File d'attente pleine, réessayez dans quelques instants"}), 503

    job_queue.put(job)
    return jsonify({"job_id": jid, "status": "queued"})

# ── Génération image ──────────────────────────────────────────────────────
@app.route("/api/generate_image", methods=["POST"])
@require_auth
def api_generate_image():
    d      = request.get_json(force=True) or {}
    prompt = d.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt vide"}), 400

    jid = uuid.uuid4().hex[:10]
    job = {
        "job_id":     jid,
        "type":       "image",
        "prompt":     prompt,
        "style":      d.get("style"),
        "resolution": d.get("resolution", "1024x1024"),
        "steps":      min(int(d.get("steps", 35)), 60),
        "guidance":   float(d.get("guidance", 7.5)),
        "seed":       int(d.get("seed", -1)),
    }

    with _jlock:
        job_status[jid] = {
            "status": "queued", "progress": 0, "step": "En attente...",
            "result": None, "error": None, "type": "image",
            "created": datetime.now(timezone.utc).isoformat(),
        }

    if job_queue.full():
        return jsonify({"error": "File d'attente pleine"}), 503

    job_queue.put(job)
    return jsonify({"job_id": jid, "status": "queued"})

# ── Status & annulation ───────────────────────────────────────────────────
@app.route("/api/status/<jid>")
@require_auth
def api_status(jid):
    with _jlock:
        j = job_status.get(jid)
    if not j:
        return jsonify({"error": "Job inconnu"}), 404
    return jsonify(j)

@app.route("/api/cancel/<jid>", methods=["POST"])
@require_auth
def api_cancel(jid):
    with _jlock:
        if jid in job_status:
            job_status[jid]["status"] = "cancelled"
            return jsonify({"ok": True})
    return jsonify({"error": "Job inconnu"}), 404

@app.route("/api/jobs")
@require_auth
def api_jobs():
    with _jlock:
        jobs = list(job_status.values())
    jobs.sort(key=lambda j: j.get("created", ""), reverse=True)
    return jsonify(jobs[:50])

# ── Fichiers ──────────────────────────────────────────────────────────────
@app.route("/api/video/<fname>")
@require_auth
def serve_video(fname):
    return send_from_directory(OUTPUT_DIR, fname)

@app.route("/api/image/<fname>")
@require_auth
def serve_image(fname):
    return send_from_directory(OUTPUT_DIR, fname)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    log.info(f"🚀 KHEDIM AI GENERATE VIDEO — Backend v13.0 sur port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
