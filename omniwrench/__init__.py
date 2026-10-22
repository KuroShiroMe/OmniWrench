"""OmniWrench - modulare Toolsammlung für Administratoren, von DarkMatter."""

APP_NAME = "OmniWrench"
APP_ID = "OmniWrench"
VENDOR = "DarkMatter"
# Name des Mutex, an dem das Windows-Installationsprogramm ein laufendes OmniWrench erkennt
# (installer/windows/OmniWrench.iss, AppMutexName)
APP_MUTEX = "DarkMatter.OmniWrench"
__version__ = "0.7.0"

# GitHub-Repository: Updates des Hauptprogramms und offizieller Tool-Store
GITHUB_REPO = "KuroShiroMe/OmniWrench"
OFFICIAL_STORE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/store/index.json"
