from .tracking import issue_token


def beacon(request):
    return {"view_token": issue_token(request)}
