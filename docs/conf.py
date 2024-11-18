# Configuration file for the Sphinx documentation builder.
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

from db2sql._version import __version__

project = "db2sql"
author = "Jacques Raphanel"
copyright = "2024, Jacques Raphanel"
release = __version__
version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "db2sql"

html_theme_options = {
    "source_repository": "https://github.com/sismicfr/python-db2sql/",
    "source_branch": "main",
    "source_directory": "docs/",
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "special-members": "__init__",
}
autodoc_member_order = "bysource"

napoleon_google_docstring = True
napoleon_numpy_docstring = False

myst_enable_extensions = ["colon_fence"]

copybutton_prompt_text = r"^\$ |^>>> "
copybutton_prompt_is_regexp = True
