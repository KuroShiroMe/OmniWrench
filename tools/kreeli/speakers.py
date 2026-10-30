"""Sprechererkennung: Stimmmerkmale, dauerhafte Sprecherprofile mit Namen und Zuordnung während einer Mitschrift.

Die Merkmale sind einfache Klangfarben-Statistiken (MFCC-Mittel und -Streuung, nur numpy) – grob, aber
lokal: Stimmen verlassen den Rechner dafür nicht. Kann der Anbieter Sprecher selbst benennen (OpenAI
gpt-4o-transcribe-diarize mit Stimmproben), hat dessen Name Vorrang.
Profile sind biometrische Daten und werden deshalb immer verschlüsselt gespeichert
(<Ablage transcripts>/speakers/profiles.owai), unabhängig von der Einstellung für Chats.
"""

from __future__ import annotations

import base64
import secrets
import time

RATE = 16000
THRESHOLD = 0.90                     # Mindest-Ähnlichkeit für „gleiche Stimme“
SAMPLE_MAX = 10.0                    # Sekunden Stimmprobe im Profil (OpenAI: 2–10 s)
_FB = None


def _mel_filters(n_fft: int = 512, n_mels: int = 26, rate: int = RATE):
    import numpy as np

    def hz2mel(h):
        return 2595.0 * np.log10(1.0 + h / 700.0)

    def mel2hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)
    mels = np.linspace(hz2mel(60.0), hz2mel(7600.0), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel2hz(mels) / rate).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        lo, mid, hi = bins[m - 1], bins[m], bins[m + 1]
        for k in range(lo, mid):
            fb[m - 1, k] = (k - lo) / max(1, mid - lo)
        for k in range(mid, hi):
            fb[m - 1, k] = (hi - k) / max(1, hi - mid)
    return fb


def embedding(samples, rate: int = RATE) -> list[float] | None:
    """Stimmmerkmale eines Abschnitts (None, wenn zu kurz oder zu leise)."""
    import numpy as np
    global _FB
    x = np.asarray(samples, dtype="float64").reshape(-1)
    if len(x) < rate // 2:
        return None
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])
    win, hop, n_fft = 400, 160, 512
    count = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(count)[:, None]
    frames = x[idx] * np.hamming(win)
    power = np.abs(np.fft.rfft(frames, n_fft)) ** 2 / n_fft
    energy = power.sum(axis=1)
    keep = energy > max(np.percentile(energy, 40), 1e-7)
    if keep.sum() < 20:
        return None
    if _FB is None:
        _FB = _mel_filters()
    logmel = np.log(_FB @ power[keep].T + 1e-10)                       # (mels, frames)
    n = logmel.shape[0]
    dct = np.cos(np.pi * np.arange(n)[:, None] * (2 * np.arange(n)[None, :] + 1) / (2 * n))
    cep = (dct @ logmel)[1:20]                                          # c1..c19
    lifter = 1 + 11 * np.sin(np.pi * np.arange(1, 20) / 22)
    cep = cep * lifter[:, None]
    vec = np.concatenate([cep.mean(axis=1), cep.std(axis=1)])
    return [round(float(v), 4) for v in vec]


def similarity(a, b) -> float:
    import numpy as np
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.asarray(a), np.asarray(b)
    den = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb) / den if den else 0.0


def blend(old, new, weight: float) -> list[float]:
    """Laufender Mittelwert (weight = Anteil des Neuen)."""
    if not old:
        return list(new)
    return [round(o * (1 - weight) + n * weight, 4) for o, n in zip(old, new)]


# ------------------------------------------------------------------ Dauerhafte Profile
class ProfileStore:
    def __init__(self, storage):
        self.storage = storage

    @property
    def base(self):
        return self.storage.path("transcripts") / "speakers" / "profiles"

    def load(self) -> list[dict]:
        try:
            data = self.storage.read_doc(self.base) or {}
        except Exception:  # noqa: BLE001 - Tresor gesperrt / Datei beschädigt
            return []
        return [p for p in data.get("profiles") or [] if isinstance(p, dict) and p.get("id")]

    def save(self, profiles: list[dict]) -> None:
        self.storage.write_doc(self.base, {"format": 1, "profiles": profiles}, encrypt=True)

    def upsert(self, name: str, emb: list[float] | None, sample: bytes = b"", profile_id: str = "") -> dict:
        profiles = self.load()
        prof = next((p for p in profiles if p["id"] == profile_id), None) if profile_id else None
        if prof is None:
            prof = next((p for p in profiles if p.get("name", "").lower() == name.lower()), None)
        if prof is None:
            prof = {"id": secrets.token_hex(4), "name": name, "embedding": [], "count": 0,
                    "created": int(time.time())}
            profiles.append(prof)
        prof["name"] = name
        if emb:
            prof["embedding"] = blend(prof.get("embedding"), emb, 1.0 / (1 + int(prof.get("count") or 0)))
            prof["count"] = int(prof.get("count") or 0) + 1
        if sample:
            prof["sample"] = base64.b64encode(sample).decode("ascii")
        prof["updated"] = int(time.time())
        self.save(profiles)
        return prof

    def rename(self, profile_id: str, name: str) -> None:
        profiles = self.load()
        for p in profiles:
            if p["id"] == profile_id:
                p["name"] = name
        self.save(profiles)

    def delete(self, profile_id: str) -> None:
        self.save([p for p in self.load() if p["id"] != profile_id])

    @staticmethod
    def samples(profiles: list[dict]) -> list[tuple[str, bytes]]:
        """(Name, WAV) für Anbieter mit bekannten Sprechern."""
        out = []
        for p in profiles:
            if p.get("sample"):
                try:
                    out.append((p["name"], base64.b64decode(p["sample"])))
                except ValueError:
                    pass
        return out


# ------------------------------------------------------------------ Zuordnung in einer Mitschrift
class SessionSpeakers:
    """Ordnet Abschnitte Sprechern zu: erst bekannte Stimmen dieser Mitschrift, dann Profile, sonst neu."""

    def __init__(self, profiles: list[dict], unknown_label: str, threshold: float = THRESHOLD,
                 speakers: dict | None = None):
        self.profiles = profiles
        self.unknown_label = unknown_label          # z. B. "Sprecher {n}"
        self.threshold = threshold
        self.speakers: dict[str, dict] = speakers if speakers is not None else {}

    def _new(self, name: str = "", profile: str = "", emb=None) -> str:
        sid = f"S{len(self.speakers) + 1}"
        self.speakers[sid] = {"name": name or self.unknown_label.format(n=len(self.speakers) + 1),
                              "profile": profile, "embedding": list(emb or []), "n": 1 if emb else 0}
        return sid

    def by_name(self, name: str, emb=None) -> str:
        for sid, s in self.speakers.items():
            if s["name"].lower() == name.lower():
                if emb:
                    self._learn(sid, emb)
                return sid
        prof = next((p for p in self.profiles if p.get("name", "").lower() == name.lower()), None)
        return self._new(name, prof["id"] if prof else "", emb)

    def _learn(self, sid: str, emb) -> None:
        s = self.speakers[sid]
        s["n"] = int(s.get("n") or 0) + 1
        s["embedding"] = blend(s.get("embedding"), emb, 1.0 / s["n"])

    def assign(self, emb, last: str = "") -> str:
        if not emb:
            return last or (next(iter(self.speakers)) if self.speakers else self._new())
        best, score = "", 0.0
        for sid, s in self.speakers.items():
            sc = similarity(emb, s.get("embedding"))
            if sc > score:
                best, score = sid, sc
        if best and score >= self.threshold:
            self._learn(best, emb)
            return best
        prof, pscore = None, 0.0
        for p in self.profiles:
            sc = similarity(emb, p.get("embedding"))
            if sc > pscore:
                prof, pscore = p, sc
        if prof is not None and pscore >= self.threshold:
            existing = next((sid for sid, s in self.speakers.items() if s.get("profile") == prof["id"]), "")
            if existing:
                self._learn(existing, emb)
                return existing
            return self._new(prof["name"], prof["id"], emb)
        return self._new(emb=emb)
