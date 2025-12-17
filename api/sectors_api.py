from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
import json
import os
import threading

from api.utils.deps import current_user

router = APIRouter(tags=["Mapping"], dependencies=[Depends(current_user)])
LOCK = threading.Lock()
SECTORS_FILE = os.path.join(os.path.dirname(__file__), "sectors.json")


class SectorIn(BaseModel):
    sector: str


class RenameSector(BaseModel):
    new_name: str


def _read_sectors():
    with LOCK:
        with open(SECTORS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    return data.get("allowed_sectors", [])


def _write_sectors(sectors):
    with LOCK:
        with open(SECTORS_FILE, "w", encoding="utf-8") as f:
            json.dump({"allowed_sectors": sectors}, f, indent=2, ensure_ascii=False)


@router.get("/sectors")
def list_sectors():
    sectors = _read_sectors()
    return {"allowed_sectors": sectors}


@router.post("/sectors", status_code=status.HTTP_201_CREATED)
def add_sector(payload: SectorIn):
    sector = payload.sector.strip()
    if not sector:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or empty 'sector' field")

    sectors = _read_sectors()
    if sector in sectors:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sector already exists")

    sectors.append(sector)
    _write_sectors(sectors)
    return {"message": "Sector added", "allowed_sectors": sectors}


@router.put("/sectors/{old_name}")
def rename_sector(old_name: str, payload: RenameSector):
    new_name = payload.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or empty 'new_name' field")

    sectors = _read_sectors()
    if old_name not in sectors:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sector '{old_name}' not found")
    if new_name in sectors:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Sector '{new_name}' already exists")

    idx = sectors.index(old_name)
    sectors[idx] = new_name
    _write_sectors(sectors)
    return {"message": "Sector renamed", "allowed_sectors": sectors}


@router.delete("/sectors/{name}")
def delete_sector(name: str):
    sectors = _read_sectors()
    if name not in sectors:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sector '{name}' not found")
    sectors = [s for s in sectors if s != name]
    _write_sectors(sectors)
    return {"message": "Sector deleted", "allowed_sectors": sectors}