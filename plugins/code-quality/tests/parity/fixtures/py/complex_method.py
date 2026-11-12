"""Target smell: Complex Method (CC 14, flat branch chain, no nesting)."""


def status_label(code):
    if code == 100:
        return "continue"
    elif code == 200:
        return "ok"
    elif code == 201:
        return "created"
    elif code == 204:
        return "no content"
    elif code == 301:
        return "moved"
    elif code == 302:
        return "found"
    elif code == 304:
        return "not modified"
    elif code == 400:
        return "bad request"
    elif code == 401:
        return "unauthorised"
    elif code == 403:
        return "forbidden"
    elif code == 404:
        return "not found"
    elif code == 409:
        return "conflict"
    elif code == 500:
        return "server error"
    return "unknown"
