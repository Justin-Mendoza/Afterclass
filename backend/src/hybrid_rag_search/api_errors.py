"""Stable public errors and server-generated request identities."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from hybrid_rag_search.authorization import AccessDenied


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def install_errors(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_identity(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": code, "message": message, "request_id": request.state.request_id}
            },
        )

    @app.exception_handler(AccessDenied)
    async def access_error(request: Request, error: AccessDenied) -> JSONResponse:
        codes = {401: "identity_required", 403: "access_denied", 404: "not_found"}
        return response(request, error.status_code, codes[error.status_code], error.detail)

    @app.exception_handler(APIError)
    async def domain_error(request: Request, error: APIError) -> JSONResponse:
        return response(request, error.status, error.code, error.message)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        codes = {
            401: "identity_required",
            403: "access_denied",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            503: "dependency_unavailable",
        }
        return response(
            request,
            error.status_code,
            codes.get(error.status_code, "request_failed"),
            str(error.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return response(request, 422, "invalid_request", "Request fields are invalid.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        return response(request, 503, "database_unavailable", "Database operation failed.")
