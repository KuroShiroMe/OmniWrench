"""Verwaltung der installierten Tools: Erkennen, Laden, Installieren, Deinstallieren."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from PySide6.QtCore import QObject, Signal

from omniwrench import __version__
from omniwrench.sdk import InstallContext, ToolBase, ToolContext

from . import i18n, prerequisites
from .i18n import tr
from .manifest import INSTALL_FILE, ManifestError, SettingDef, ToolManifest, load_settings_schema, validate_package
from .paths import TOOL_DATA_DIR, TOOLS_DIR
from .tool_settings import ToolSettingsStore
from .vault import Vault
from .versioning import is_newer

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


@dataclass
class InstalledTool:
    manifest: ToolManifest
    path: Path
    schema: list[SettingDef]
    settings: ToolSettingsStore
    error: str = ""                 # gesetzt, wenn das Tool defekt ist

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def data_dir(self) -> Path:
        return TOOL_DATA_DIR / self.manifest.id

    @property
    def icon_path(self) -> Path | None:
        if self.manifest.icon:
            p = self.path / self.manifest.icon
            return p if p.exists() else None
        return None


def _module_prefix(tool_id: str) -> str:
    return "omniwrench_tool_" + "".join(c if c.isalnum() else "_" for c in tool_id)


def _rmtree(path: Path) -> None:
    def make_writable_and_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onexc=make_writable_and_retry)


class ToolManager(QObject):
    toolsChanged = Signal()

    def __init__(self, vault: Vault):
        super().__init__()
        self.vault = vault
        self.tools: dict[str, InstalledTool] = {}
        self.refresh()

    # ------------------------------------------------------------ Erkennen
    def refresh(self) -> None:
        i18n.clear_cache()  # Sprachdateien neu einlesen (nach Installation/Update)
        tools: dict[str, InstalledTool] = {}
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        for d in sorted(TOOLS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                manifest = ToolManifest.load(d)
                schema = load_settings_schema(d)
                tools[manifest.id] = InstalledTool(manifest, d, schema, self._settings_for(manifest.id, schema))
            except Exception as exc:  # noqa: BLE001
                log.warning("Tool in %s konnte nicht gelesen werden: %s", d, exc)
        self.tools = tools
        self.toolsChanged.emit()

    def _settings_for(self, tool_id: str, schema: list[SettingDef]) -> ToolSettingsStore:
        old = self.tools.get(tool_id)
        if old and old.schema == schema:
            return old.settings  # Listener bestehender Instanzen beibehalten
        return ToolSettingsStore(tool_id, schema, self.vault)

    def get(self, tool_id: str) -> InstalledTool | None:
        return self.tools.get(tool_id)

    # --------------------------------------------------------------- Laden
    def _import_entry(self, tool: InstalledTool) -> type[ToolBase]:
        module_name, _, class_name = tool.manifest.entry.partition(":")
        pkg = _module_prefix(tool.id)

        lib = tool.path / "_lib"
        if lib.is_dir() and str(lib) not in sys.path:
            sys.path.insert(0, str(lib))

        if pkg not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                pkg, tool.path / "__init__.py", submodule_search_locations=[str(tool.path)]
            )
            package = importlib.util.module_from_spec(spec) if spec else ModuleType(pkg)
            package.__path__ = [str(tool.path)]
            sys.modules[pkg] = package
            if (tool.path / "__init__.py").exists() and spec and spec.loader:
                spec.loader.exec_module(package)

        module = importlib.import_module(f"{pkg}.{module_name}")
        cls = getattr(module, class_name or "Tool", None)
        if not (isinstance(cls, type) and issubclass(cls, ToolBase)):
            raise ManifestError(tr("err.entry_not_toolbase", entry=tool.manifest.entry))
        return cls

    def create_instance(self, tool_id: str, notify: Callable[[str], None] | None = None,
                        open_settings: Callable[[], None] | None = None) -> ToolBase:
        tool = self.tools[tool_id]
        cls = self._import_entry(tool)
        tool.data_dir.mkdir(parents=True, exist_ok=True)
        ctx = ToolContext(tool.manifest, tool.path, tool.data_dir, tool.settings, self.vault,
                          notify=notify, open_settings=open_settings)
        return cls(ctx)

    def _unload_modules(self, tool_id: str) -> None:
        prefix = _module_prefix(tool_id)
        for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
            del sys.modules[name]

    # ------------------------------------------------------- Installation
    def install_zip(self, zip_path: Path, progress: Progress, expected_sha256: str = "") -> ToolManifest:
        if expected_sha256:
            digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            if digest.lower() != expected_sha256.lower():
                raise ManifestError(tr("err.checksum"))
            progress(tr("prog.checksum_ok"))
        with tempfile.TemporaryDirectory(prefix="omniwrench_pkg_") as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    target = (tmp_path / member).resolve()
                    if not target.is_relative_to(tmp_path.resolve()):
                        raise ManifestError(tr("err.unsafe_path", path=member))
                zf.extractall(tmp_path)
            # Paket darf die Dateien direkt oder in einem Unterordner enthalten
            root = tmp_path
            entries = [p for p in tmp_path.iterdir()]
            if not (root / "tool.json").exists() and len(entries) == 1 and entries[0].is_dir():
                root = entries[0]
            return self.install_dir(root, progress)

    def install_dir(self, src: Path, progress: Progress) -> ToolManifest:
        manifest = validate_package(src)
        progress(tr("prog.package_ok", name=manifest.display_name, version=manifest.version))
        if is_newer(manifest.min_app_version, __version__):
            raise ManifestError(tr("err.min_app_version", required=manifest.min_app_version, installed=__version__))
        if "windows" not in [p.lower() for p in manifest.platforms] and sys.platform == "win32":
            raise ManifestError(tr("err.platform"))

        target = TOOLS_DIR / manifest.id
        backup = TOOLS_DIR / f".backup-{manifest.id}"
        old_version = None
        if target.exists():
            try:
                old_version = ToolManifest.load(target).version
            except ManifestError:
                pass
            _rmtree(backup)
            target.rename(backup)
            progress(tr("prog.backup", version=old_version))

        self._unload_modules(manifest.id)
        try:
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_lib"))
            i18n.clear_cache()
            schema = load_settings_schema(target)
            settings = self._settings_for(manifest.id, schema)
            ctx = self._install_context(manifest, target, settings, progress)

            prerequisites.install_requirements(manifest.requirements, ctx.pip_install, progress)

            installer = self._load_installer(manifest.id, target)
            if old_version and hasattr(installer, "update"):
                progress(tr("prog.run_update", old=old_version, new=manifest.version))
                installer.update(ctx, old_version)
            elif hasattr(installer, "install"):
                progress(tr("prog.run_install"))
                installer.install(ctx)
            if hasattr(installer, "check"):
                missing = installer.check(ctx) or []
                if missing:
                    raise RuntimeError(tr("err.still_missing") + "\n- " + "\n- ".join(missing))
        except BaseException:
            progress(tr("prog.rollback"))
            _rmtree(target)
            if backup.exists():
                backup.rename(target)
            self.refresh()
            raise
        _rmtree(backup)
        progress(tr("prog.installed", name=manifest.display_name, version=manifest.version))
        self.refresh()
        return manifest

    def _install_context(self, manifest: ToolManifest, tool_dir: Path, settings: ToolSettingsStore,
                         progress: Progress) -> InstallContext:
        data_dir = TOOL_DATA_DIR / manifest.id
        data_dir.mkdir(parents=True, exist_ok=True)
        return InstallContext(manifest, tool_dir, data_dir, settings, self.vault, progress=progress)

    def _load_installer(self, tool_id: str, tool_dir: Path) -> ModuleType:
        name = _module_prefix(tool_id) + "__install"
        spec = importlib.util.spec_from_file_location(name, tool_dir / INSTALL_FILE)
        if not spec or not spec.loader:
            raise ManifestError(tr("err.installer_load"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def check_tool(self, tool_id: str) -> list[str]:
        """Ruft check() aus install.py auf und liefert fehlende Voraussetzungen."""
        tool = self.tools[tool_id]
        installer = self._load_installer(tool_id, tool.path)
        if not hasattr(installer, "check"):
            return []
        ctx = self._install_context(tool.manifest, tool.path, tool.settings, lambda m: None)
        return list(installer.check(ctx) or [])

    def repair(self, tool_id: str, progress: Progress) -> None:
        """Führt Voraussetzungen + install() erneut aus."""
        tool = self.tools[tool_id]
        ctx = self._install_context(tool.manifest, tool.path, tool.settings, progress)
        prerequisites.install_requirements(tool.manifest.requirements, ctx.pip_install, progress)
        installer = self._load_installer(tool_id, tool.path)
        if hasattr(installer, "install"):
            installer.install(ctx)
        progress(tr("prog.repaired"))

    # ---------------------------------------------------- Deinstallation
    def uninstall(self, tool_id: str, remove_settings: bool, progress: Progress) -> None:
        tool = self.tools.get(tool_id)
        if not tool:
            return
        try:
            installer = self._load_installer(tool_id, tool.path)
            if hasattr(installer, "uninstall"):
                progress(tr("prog.run_uninstall"))
                installer.uninstall(self._install_context(tool.manifest, tool.path, tool.settings, progress))
        except Exception as exc:  # noqa: BLE001 - Deinstallation trotzdem fortsetzen
            progress(tr("prog.uninstall_warning", error=exc))
        self._unload_modules(tool_id)
        _rmtree(tool.path)
        if remove_settings:
            tool.settings.delete_all()
            _rmtree(tool.data_dir)
            progress(tr("prog.settings_removed"))
        progress(tr("prog.uninstalled", name=tool.manifest.display_name))
        self.refresh()
