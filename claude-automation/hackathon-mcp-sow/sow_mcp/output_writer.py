from pathlib import Path

# Absolute path to the repo's output/ directory, regardless of process cwd.
_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "output"


class OutputWriter:
    """All file I/O for generated artifacts goes through here."""

    def __init__(self, customer: str, base_dir: Path | None = None) -> None:
        root = base_dir if base_dir is not None else _DEFAULT_OUTPUT
        self.customer = customer.replace(" ", "_")
        self.dir = root / self.customer
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, filename: str) -> Path:
        return self.dir / filename

    def write_text(self, filename: str, content: str) -> Path:
        p = self.path(filename)
        p.write_text(content, encoding="utf-8")
        return p

    def write_bytes(self, filename: str, content: bytes) -> Path:
        p = self.path(filename)
        p.write_bytes(content)
        return p
