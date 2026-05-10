class SafetyViolationError(Exception):
    pass

class MessageTooLongError(Exception):
    pass

FORBIDDEN_PHRASES = [
    "buy here",
    "sell here",
    "guaranteed",
    "risk-free",
    "100%",
    "must enter",
    "easy money",
    "signal to enter now",
    "financial advice"
]

def check_safety(rendered_output: str) -> None:
    """
    Checks the rendered output against forbidden language.
    Raises SafetyViolationError if any forbidden phrase is found.
    Case-insensitive check.
    """
    # Remove the required footer before checking so it doesn't trigger on its own "financial advice"
    lower_output = rendered_output.lower().replace("not financial advice", "")
    
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in lower_output:
            raise SafetyViolationError(f"Safety Check Failed: Output contains forbidden phrase '{phrase}'")

def check_length(rendered_output: str) -> None:
    """
    Checks the rendered output length.
    Raises MessageTooLongError if it exceeds 1900 characters.
    """
    if len(rendered_output) > 1900:
        raise MessageTooLongError(f"Message is too long: {len(rendered_output)} characters (limit 1900)")
