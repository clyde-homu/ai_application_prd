"""PDF rendering for SACS and TCC reports via WeasyPrint.

The same Jinja templates that drive the on-screen preview are rendered to PDF,
so the printed output and the browser preview stay in lockstep. WeasyPrint is
imported lazily so that pure-calculation unit tests don't require its native
libraries (pango/cairo) to be installed.
"""

from __future__ import annotations

from flask import render_template


def _build_context(report) -> dict:
    return {
        "report": report,
        "client": report.client,
        "c": report.computed(),
        "groups": report.grouped(),
    }


def _html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # lazy import — needs native libs

    return HTML(string=html).write_pdf()


def render_sacs_pdf(report) -> bytes:
    html = render_template("sacs.html", **_build_context(report))
    return _html_to_pdf(html)


def render_tcc_pdf(report) -> bytes:
    html = render_template("tcc.html", **_build_context(report))
    return _html_to_pdf(html)
