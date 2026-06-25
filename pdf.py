"""PDF rendering for SACS and TCC reports via WeasyPrint.

The same Jinja templates that drive the on-screen preview are rendered to PDF,
so the printed output and the browser preview stay in lockstep. WeasyPrint is
imported lazily so that pure-calculation unit tests don't require its native
libraries (pango/cairo) to be installed.
"""

from __future__ import annotations

import os

from flask import render_template

# Where the GTK3 runtime DLLs live on Windows. WeasyPrint resolves dependent
# DLLs (glib, libffi, …) via PATH, so add_dll_directory alone is not enough.
_WINDOWS_GTK_DIRS = [
    r"C:\Program Files\GTK3-Runtime Win64\bin",
    r"C:\Program Files (x86)\GTK3-Runtime Win64\bin",
]


def _ensure_native_libs() -> None:
    """On Windows, make WeasyPrint's GTK runtime DLLs discoverable.

    No-op on Linux/macOS (e.g. Railway), where the libraries are installed
    system-wide by ``nixpacks.toml``. Set ``WEASYPRINT_DLL_DIRECTORIES`` to
    override the location.
    """
    if os.name != "nt":
        return
    candidates = []
    override = os.environ.get("WEASYPRINT_DLL_DIRECTORIES")
    if override:
        candidates.extend(override.split(os.pathsep))
    candidates.extend(_WINDOWS_GTK_DIRS)
    for directory in candidates:
        if directory and os.path.isdir(directory):
            try:
                os.add_dll_directory(directory)
            except (OSError, AttributeError):
                pass
            if directory.lower() not in os.environ.get("PATH", "").lower():
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
            return


def _build_context(report) -> dict:
    return {
        "report": report,
        "client": report.client,
        "c": report.computed(),
        "groups": report.grouped(),
    }


def _html_to_pdf(html: str) -> bytes:
    _ensure_native_libs()
    from weasyprint import HTML  # lazy import — needs native libs

    return HTML(string=html).write_pdf()


def render_sacs_pdf(report) -> bytes:
    html = render_template("sacs.html", **_build_context(report))
    return _html_to_pdf(html)


def render_tcc_pdf(report) -> bytes:
    html = render_template("tcc.html", **_build_context(report))
    return _html_to_pdf(html)
