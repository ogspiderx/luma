class LumaError(Exception):
    user_message = "Something went wrong."

    def __init__(self, message=None):
        self.user_message = message or self.user_message
        super().__init__(self.user_message)


class ToolInstallError(LumaError):
    pass


class InvalidURLError(LumaError):
    pass


class UnsafePathError(LumaError):
    pass
