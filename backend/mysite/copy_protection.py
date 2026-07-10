from django.http import HttpResponse


class DisableCopyMiddleware:
    """
    Injects client-side guards to discourage copy/cut/select operations on HTML pages.
    """

    STYLE_SNIPPET = (
        "<style id=\"disable-copy-style\">"
        "body{-webkit-user-select:none;-moz-user-select:none;-ms-user-select:none;user-select:none;}"
        "input,textarea{user-select:text;-webkit-user-select:text;-moz-user-select:text;}"
        "</style>"
    )

    SCRIPT_SNIPPET = (
        "<script id=\"disable-copy-script\">"
        "(function(){"
        "var stop=function(e){e.preventDefault();};"
        "document.addEventListener('copy',stop,true);"
        "document.addEventListener('cut',stop,true);"
        "document.addEventListener('dragstart',stop,true);"
        "document.addEventListener('contextmenu',stop,true);"
        "document.addEventListener('selectstart',function(e){"
        "var t=e.target&&e.target.tagName?e.target.tagName.toUpperCase():'';"
        "if(t!=='INPUT'&&t!=='TEXTAREA'){e.preventDefault();}"
        "},true);"
        "document.addEventListener('keydown',function(e){"
        "var k=(e.key||'').toLowerCase();"
        "if((e.ctrlKey||e.metaKey)&&(k==='c'||k==='x')){e.preventDefault();}"
        "},true);"
        "})();"
        "</script>"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return self.process_response(request, response)

    def process_response(self, request, response: HttpResponse):
        # Keep auth/admin pages untouched.
        path = request.path or ""
        if "/accounts/" in path or "/admin/" in path:
            return response

        if getattr(response, "streaming", False):
            return response
        content_type = (response.get("Content-Type") or "").lower()
        if "text/html" not in content_type:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except Exception:
            return response

        if "disable-copy-script" in html:
            return response

        if "</head>" in html:
            html = html.replace("</head>", f"{self.STYLE_SNIPPET}</head>", 1)
        else:
            html = f"{self.STYLE_SNIPPET}{html}"

        if "</body>" in html:
            html = html.replace("</body>", f"{self.SCRIPT_SNIPPET}</body>", 1)
        else:
            html = f"{html}{self.SCRIPT_SNIPPET}"

        response.content = html.encode(response.charset or "utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
