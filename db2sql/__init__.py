"""db2sql — clean-architecture database-to-PostgreSQL dumper."""

from db2sql import const
from db2sql._version import __author__, __copyright__, __version__

__all__ = [
    "__author__",
    "__copyright__",
    "__version__",
    "const",
]
__all__.extend(const.__all__)
