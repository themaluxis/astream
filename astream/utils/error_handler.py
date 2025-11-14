from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from astream.utils.logger import logger


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    try:
        if isinstance(exc, HTTPException):
            logger.warning(f"Exception HTTP: {exc.status_code} - {exc.detail}")
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": "HTTP_ERROR",
                    "message": exc.detail
                }
            )

        else:
            logger.error(f"Exception non gérée: {str(exc)}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "Une erreur interne s'est produite"
                }
            )

    except Exception as handler_error:
        logger.error(f"Erreur dans le handler d'exception: {handler_error}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "HANDLER_ERROR",
                "message": "Erreur critique du système"
            }
        )
