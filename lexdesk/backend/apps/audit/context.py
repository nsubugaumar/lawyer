from contextvars import ContextVar

# Who is making the current request, and from where. Set by the middleware,
# read by audit.record(), so service code never has to pass the request down.
request_ip: ContextVar[str | None] = ContextVar("request_ip", default=None)
request_user_agent: ContextVar[str] = ContextVar("request_user_agent", default="")
