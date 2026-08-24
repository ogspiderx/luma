NARROW_COLUMNS = 88

ROOMY_COLUMNS = 132

SHORT_ROWS = 26

SIZE_CLASSES = ("-narrow", "-roomy", "-short")


def classes_for(width, height):
    wanted = set()
    if width < NARROW_COLUMNS:
        wanted.add("-narrow")
    elif width >= ROOMY_COLUMNS:
        wanted.add("-roomy")
    if height < SHORT_ROWS:
        wanted.add("-short")
    return wanted


class SizeAware:
    def apply_size_classes(self, width=None, height=None) -> None:
        if width is None or height is None:
            size = self.app.size
            width, height = size.width, size.height
        wanted = classes_for(width, height)
        for name in SIZE_CLASSES:
            self.set_class(name in wanted, name)

    def on_resize(self, event) -> None:
        self.apply_size_classes(event.size.width, event.size.height)
