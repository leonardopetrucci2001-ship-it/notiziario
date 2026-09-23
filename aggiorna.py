"""Scarica le notizie dai feed in fonti.json, sceglie le più rilevanti e scrive
docs/giorni/AAAA-MM-GG.json (letto dalla pagina). Solo libreria standard.

Variabili d'ambiente facoltative:
  GEMINI_API_KEY  se c'è, Gemini sceglie le notizie e scrive i riassunti
  NTFY_TOPIC      se c'è, manda la notifica al telefono tramite ntfy.sh
  PAGINA_URL      indirizzo della pagina, aperto quando tocchi la notifica
"""
import difflib
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

QUI = Path(__file__).parent
GIORNI = QUI / "docs" / "giorni"
try:
    ROMA = ZoneInfo("Europe/Rome")
except Exception:  # Windows senza tzdata: basta per le prove in locale
    ROMA = timezone(timedelta(hours=2))
ATOM = "{http://www.w3.org/2005/Atom}"
UA = "Mozilla/5.0 (notiziario personale; +https://github.com)"
GIORNI_TENUTI = 14
MODELLI_GEMINI = ["gemini-flash-latest", "gemini-2.5-flash"]


def scarica(url, dati=None, intestazioni=None, attesa=20):
    h = {"User-Agent": UA, **(intestazioni or {})}
    req = urllib.request.Request(url, data=dati, headers=h)
    with urllib.request.urlopen(req, timeout=attesa) as r:
        return r.read()


def pulisci(testo, limite=320):
    testo = html.unescape(re.sub(r"<[^>]+>", " ", testo or ""))
    testo = re.sub(r"\s+", " ", testo).strip()
    testo = re.sub(r"\s*The post .* appeared first on .*$", "", testo)  # coda dei feed WordPress
    return testo if len(testo) <= limite else testo[:limite].rsplit(" ", 1)[0] + "…"


def data_di(voce):
    for tag in ("pubDate", f"{ATOM}published", f"{ATOM}updated", "{http://purl.org/dc/elements/1.1/}date"):
        v = voce.findtext(tag)
        if not v:
            continue
        v = v.strip()
        try:
            d = email.utils.parsedate_to_datetime(v)
        except (TypeError, ValueError):
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def leggi_feed(fonte):
    url = fonte.get("url") or (
        "https://news.google.com/rss/search?q=" + urllib.parse.quote(fonte["cerca"]) + "&hl=it&gl=IT&ceid=IT:it"
    )
    radice = ET.fromstring(scarica(url))
    voci = radice.findall(".//item") or radice.findall(f".//{ATOM}entry")
    notizie = []
    for v in voci:
        titolo = pulisci(v.findtext("title") or v.findtext(f"{ATOM}title"), 220)
        link = (v.findtext("link") or "").strip()
        if not link:
            el = v.find(f"{ATOM}link[@rel='alternate']")
            if el is None:
                el = v.find(f"{ATOM}link")
            link = el.get("href", "") if el is not None else ""
        testo = v.findtext("description") or v.findtext(f"{ATOM}summary") or v.findtext(f"{ATOM}content")
        nome = fonte["nome"]
        if fonte.get("cerca"):
            # Google News: "Titolo - Testata"; la testata vera è nel tag <source>
            nome = (v.findtext("source") or nome).strip()
            titolo = re.sub(r"\s+-\s+" + re.escape(nome) + r"$", "", titolo)
            testo = ""
        if not titolo or not link:
            continue
        notizie.append({
            "titolo": titolo,
            "link": link,
            "fonte": nome,
            "testo": pulisci(testo),
            "data": data_di(v),
        })
    return notizie


def chiave(titolo):
    return re.sub(r"[^a-z0-9àèéìòù ]", "", titolo.lower())


def doppione(titolo, visti):
    k = chiave(titolo)
    return any(difflib.SequenceMatcher(None, k, altro).ratio() > 0.78 for altro in visti)


def raccogli(config, adesso):
    visti_link, visti_titoli, candidati, errori = set(), [], {}, []
    for arg in config["argomenti"]:
        soglia = adesso - timedelta(hours=arg["ore"])
        parole = [p.lower() for p in arg.get("parole_chiave", [])]
        lista = []
        for i, fonte in enumerate(arg["fonti"]):
            try:
                notizie = leggi_feed(fonte)
            except Exception as e:  # una fonte giù non deve fermare le altre
                errori.append(f"{fonte['nome']}: {type(e).__name__}")
                continue
            for n in notizie:
                testo = (n["titolo"] + " " + n["testo"]).lower()
                if fonte.get("solo_se") and not any(p in testo for p in fonte["solo_se"]):
                    continue
                if any(p in testo for p in fonte.get("escludi", [])):
                    continue
                if n["data"] and n["data"] < soglia:
                    continue
                if n["link"] in visti_link or doppione(n["titolo"], visti_titoli):
                    continue
                n["origine"] = i
                visti_link.add(n["link"])
                visti_titoli.append(chiave(n["titolo"]))
                eta = (adesso - (n["data"] or soglia)).total_seconds() / 3600
                n["punti"] = sum(p in testo for p in parole) * 2 - eta / arg["ore"] * 3
                lista.append(n)
        lista.sort(key=lambda n: n["punti"], reverse=True)
        candidati[arg["id"]] = lista[:30]
    return candidati, errori


def chiedi_a_gemini(config, candidati, chiave_api):
    elenco = {
        arg["id"]: [
            {"n": i, "titolo": n["titolo"], "fonte": n["fonte"], "testo": n["testo"][:200]}
            for i, n in enumerate(candidati[arg["id"]])
        ]
        for arg in config["argomenti"]
    }
    nomi = {a["id"]: f'{a["nome"]} (massimo {a["max"]})' for a in config["argomenti"]}
    istruzioni = f"""Sei il redattore della rassegna del mattino di una sola persona.
Chi legge: {config["profilo"]}

Per ogni argomento scegli le notizie più utili per questa persona, nell'ordine di importanza:
{json.dumps(nomi, ensure_ascii=False)}
Scarta doppioni, pubblicità, gossip, notizie locali irrilevanti e articoli che non riguardano davvero l'argomento.
Per ogni notizia scelta scrivi un riassunto in italiano di 1 o 2 frasi che dica il fatto e perché conta. Se il titolo è in inglese, scrivi anche un titolo italiano breve.
Poi scrivi "in_breve": 3 frasi, le tre cose da sapere oggi in assoluto.
Stile: italiano semplice e diretto, niente trattini lunghi, niente frecce, niente enfasi.

Rispondi solo con JSON in questa forma:
{{"in_breve": ["...", "...", "..."], "scelte": {{"<id argomento>": [{{"n": 0, "titolo_it": "...", "riassunto": "..."}}]}}}}

Candidati:
{json.dumps(elenco, ensure_ascii=False)}"""
    corpo = json.dumps({
        "contents": [{"parts": [{"text": istruzioni}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }).encode()
    ultimo_errore = None
    for modello in MODELLI_GEMINI:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent"
        try:
            r = json.loads(scarica(url, corpo, {"Content-Type": "application/json", "x-goog-api-key": chiave_api}, 120))
            return json.loads(r["candidates"][0]["content"]["parts"][0]["text"]), modello
        except Exception as e:
            ultimo_errore = e
    raise RuntimeError(f"Gemini non ha risposto: {ultimo_errore}")


def componi(config, candidati, adesso):
    risposta, modello = None, None
    chiave_api = os.environ.get("GEMINI_API_KEY")
    if chiave_api:
        try:
            risposta, modello = chiedi_a_gemini(config, candidati, chiave_api)
        except Exception as e:
            print(f"! {e}. Uso la selezione automatica.", file=sys.stderr)

    argomenti = []
    for arg in config["argomenti"]:
        lista = candidati[arg["id"]]
        if risposta:
            scelte = []
            for s in risposta.get("scelte", {}).get(arg["id"], [])[: arg["max"]]:
                if isinstance(s.get("n"), int) and 0 <= s["n"] < len(lista):
                    n = dict(lista[s["n"]])
                    n["titolo_it"] = s.get("titolo_it") or ""
                    n["riassunto"] = s.get("riassunto") or ""
                    scelte.append(n)
        else:
            # senza AI: al massimo 2 notizie per feed, così una sola fonte non riempie tutto
            scelte, per_feed = [], {}
            for n in lista:
                if len(scelte) < arg["max"] and per_feed.get(n["origine"], 0) < 2:
                    per_feed[n["origine"]] = per_feed.get(n["origine"], 0) + 1
                    scelte.append(dict(n, riassunto=n["testo"]))
        voci = [{
            "titolo": n["titolo"],
            "titolo_it": n.get("titolo_it", "") if n.get("titolo_it", "").strip() != n["titolo"] else "",
            "riassunto": n["riassunto"],
            "fonte": n["fonte"],
            "link": n["link"],
            "ora": n["data"].isoformat() if n["data"] else None,
        } for n in scelte]
        argomenti.append({"id": arg["id"], "nome": arg["nome"], "notizie": voci})

    return {
        "giorno": adesso.astimezone(ROMA).date().isoformat(),
        "creato": adesso.isoformat(timespec="seconds"),
        "in_breve": (risposta or {}).get("in_breve", [])[:3],
        "modello": modello,
        "argomenti": argomenti,
    }


def salva(uscita):
    GIORNI.mkdir(parents=True, exist_ok=True)
    (GIORNI / f"{uscita['giorno']}.json").write_text(json.dumps(uscita, ensure_ascii=False, indent=1), encoding="utf-8")
    giorni = sorted((p.stem for p in GIORNI.glob("????-??-??.json")), reverse=True)
    for vecchio in giorni[GIORNI_TENUTI:]:
        (GIORNI / f"{vecchio}.json").unlink()
    (GIORNI / "indice.json").write_text(json.dumps(giorni[:GIORNI_TENUTI]), encoding="utf-8")


def notifica(uscita):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    righe = uscita["in_breve"] or [
        (a["notizie"][0].get("titolo_it") or a["notizie"][0]["titolo"]) for a in uscita["argomenti"] if a["notizie"]
    ][:3]
    totale = sum(len(a["notizie"]) for a in uscita["argomenti"])
    messaggio = {
        "topic": topic,
        "title": f"Buongiorno, {totale} notizie per oggi",
        "message": "\n".join(f"• {r}" for r in righe),
        "tags": ["sunrise"],
    }
    if os.environ.get("PAGINA_URL"):
        messaggio["click"] = os.environ["PAGINA_URL"]
    scarica("https://ntfy.sh/", json.dumps(messaggio).encode(), {"Content-Type": "application/json"})
    print("Notifica inviata.")


def main():
    config = json.loads((QUI / "fonti.json").read_text(encoding="utf-8"))
    adesso = datetime.now(timezone.utc)
    candidati, errori = raccogli(config, adesso)
    for e in errori:
        print(f"! fonte non raggiungibile: {e}", file=sys.stderr)
    uscita = componi(config, candidati, adesso)
    uscita["fonti_giu"] = errori
    salva(uscita)
    for a in uscita["argomenti"]:
        print(f"{a['nome']}: {len(a['notizie'])} notizie")
    if "--senza-notifica" not in sys.argv:
        notifica(uscita)


if __name__ == "__main__":
    main()
