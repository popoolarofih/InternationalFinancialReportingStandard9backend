# Update api/main.py (add the include_router)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from api.routers import auth, usermanagement, msal, user_settings, model, activities, reports, otherinputs, dashboard
from api.database import engine
from api.sectors_api import router as sectors_router  # add import for sectors router
from api.services.dashboard_service import fetch_and_store_dashboard_data

# Initialize FastAPI app
app = FastAPI(
    title="Tatum Bank IFRS9 API",
    description="API for IFRS9 model implementation for Tatum Bank, including authentication and user management.",
    version="1.0.0"
)

# Add CORS middleware (adjust allow_origins for your frontend domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
SQLModel.metadata.create_all(bind=engine)

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Include routers
app.include_router(auth.router, prefix="/auth")
app.include_router(usermanagement.router, prefix="/user")
app.include_router(msal.router)
app.include_router(user_settings.router, prefix="/settings")
app.include_router(model.router)
app.include_router(activities.router)
app.include_router(reports.router)
app.include_router(otherinputs.router)
app.include_router(sectors_router, prefix="/api") 
app.include_router(dashboard.router)
 

@app.on_event("startup")
async def startup_event():
    # Add job to fetch dashboard data every 30 minutes
    scheduler.add_job(
        fetch_and_store_dashboard_data,
        trigger=IntervalTrigger(minutes=30),
        id="fetch_dashboard_data",
        name="Fetch and store dashboard data"
    )
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

@app.get("/")
async def root():
    return {"message": "Welcome to Tatum Bank IFRS9 API"}
