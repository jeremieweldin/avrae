from cogs5e.models.errors import AvraeException


class EvaluationError(AvraeException):
    """Raised when a cvar evaluation causes an error."""

    def __init__(self, original, expression=None):
        super().__init__(f"Error evaluating expression: {original}")
        self.original = original
        self.expression = expression


class FunctionRequiresCharacter(AvraeException):
    """
    Raised when a function that requires a character is called without one.
    """

    def __init__(self, msg=None):
        super().__init__(msg or "This alias requires an active character.")


class CollectionNotFound(AvraeException):
    """Raised when a WorkshopCollection is not found."""

    def __init__(self, msg=None):
        super().__init__(msg or "The specified collection was not found.")


class CollectableNotFound(AvraeException):
    """Raised when a collectable (alias/snippet) is not found in a collection."""

    def __init__(self, msg=None):
        super().__init__(msg or "The specified object was not found.")