from fastapi import FastAPI

from api.errors import register_exception_handlers
from identity.interface.api.routes import router as identity_router
from resources.interface.api.routes import router as resources_router


def create_app() -> FastAPI:
    app = FastAPI(title="TenantPlatform API", version="0.2.0")
    register_exception_handlers(app)
    app.include_router(identity_router)
    app.include_router(resources_router)
    return app


app = create_app()
