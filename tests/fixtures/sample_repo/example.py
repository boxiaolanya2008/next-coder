"""Old-style Python class that the demo Implementer will refactor to @dataclass."""


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def distance_to(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        return (dx * dx + dy * dy) ** 0.5


def make_point(x, y):
    return Point(x, y)
