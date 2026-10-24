"""Every error response is the contract's Error object: {"code", "message"}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "notFound", f"{what} not found")


def forbidden(message: str) -> ApiError:
    return ApiError(403, "forbidden", message)


_CODES = {400: "badRequest", 401: "unauthorized", 403: "forbidden", 404: "notFound", 405: "methodNotAllowed"}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _CODES.get(exc.status_code, "error")
        return JSONResponse({"code": code, "message": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for e in exc.errors()[:5]:
            where = "/".join(str(p) for p in e.get("loc", ()))
            parts.append(f"{where}: {e.get('msg')}")
        return JSONResponse({"code": "invalid", "message": "; ".join(parts)}, status_code=422)
