from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_exception_handlers
from authz.interface.api.routes import router as authz_router
from identity.interface.api.routes import router as identity_router
from identity.interface.api.sa_routes import router as service_accounts_router
from resources.interface.api.routes import router as resources_router
from shared.settings import settings
from tenant.interface.api.routes import router as tenant_router
from vendor.interface.api.routes import router as vendor_router


def create_app() -> FastAPI:
    app = FastAPI(title="TenantPlatform API", version="0.2.0")
    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "X-Request-Id"],
        )
    register_exception_handlers(app)
    app.include_router(identity_router)
    app.include_router(resources_router)
    app.include_router(authz_router)
    app.include_router(tenant_router)
    app.include_router(service_accounts_router)
    app.include_router(vendor_router)
    return app


app = create_app()
