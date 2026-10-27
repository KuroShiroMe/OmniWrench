"""OmniWrench - modulare Toolsammlung für Administratoren, von KuroShiro."""

APP_NAME = "OmniWrench"
APP_ID = "OmniWrench"
VENDOR = "KuroShiro"
# Frühere Herstellernamen (Datenordner werden beim Start übernommen, core/paths.py)
LEGACY_VENDORS = ("DarkMatter",)
# Name des Mutex, an dem das Windows-Installationsprogramm ein laufendes OmniWrench erkennt
# (installer/windows/OmniWrench.iss, AppMutexName)
APP_MUTEX = "KuroShiro.OmniWrench"
__version__ = "0.8.1"

# GitHub-Repository: Updates des Hauptprogramms und offizieller Tool-Store
GITHUB_REPO = "KuroShiroMe/OmniWrench"
OFFICIAL_STORE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/store/index.json"
