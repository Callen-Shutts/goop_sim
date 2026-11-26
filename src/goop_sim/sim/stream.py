class Stream(dict):
    """Gallons of each species, keyed by species letter. A dict with a few helpers."""

    def copy(self) -> "Stream":
        return Stream(self)

    def total(self) -> float:
        return sum(self.values())

    def scaled(self, factor: float) -> "Stream":
        return Stream({k: v * factor for k, v in self.items()})

    def add(self, other: dict) -> None:
        for k, v in other.items():
            self[k] = self.get(k, 0.0) + v

    def take(self, gal: float) -> "Stream":
        """Remove up to `gal` gallons, keeping the composition. Returns what was removed."""
        total = self.total()
        if total <= 0 or gal <= 0:
            return Stream()
        part = self.scaled(min(1.0, gal / total))
        for k, v in part.items():
            self[k] = max(0.0, self[k] - v)
        return part

    def fraction(self, species: str) -> float:
        total = self.total()
        return self.get(species, 0.0) / total if total > 0 else 0.0

    def dominant(self) -> str | None:
        live = {k: v for k, v in self.items() if v > 1e-9}
        return max(live, key=live.get) if live else None
