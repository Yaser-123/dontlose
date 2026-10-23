class AppError(Exception):
    """Expected failure with a message that can be shown to the user."""


class OcrError(AppError):
    pass


class OllamaError(AppError):
    pass
