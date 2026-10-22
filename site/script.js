// Download-Links auf das neueste GitHub-Release umstellen. Ohne Netz oder bei API-Limit
// bleiben die fest eingetragenen Links (Version im HTML) stehen.
(async () => {
  try {
    const res = await fetch("https://api.github.com/repos/KuroShiroMe/OmniWrench/releases/latest",
                            { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) return;
    const release = await res.json();
    const version = (release.tag_name || "").replace(/^v/, "");
    for (const link of document.querySelectorAll("a[data-asset]")) {
      const asset = (release.assets || []).find(a => a.name.endsWith(link.dataset.asset));
      if (asset) link.href = asset.browser_download_url;
    }
    if (version) {
      document.getElementById("version-label").textContent = `Version ${version}`;
      document.getElementById("release-info").textContent = `Aktuelle Version: ${version}`;
    }
  } catch (e) {
    // Fest eingetragene Links genügen
  }
})();
