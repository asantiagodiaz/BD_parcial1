import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

ROUTE_PATTERN = r"^[A-Z]{3}-[A-Z]{3}$"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class FlightIn(BaseModel):
    flight_id: str = Field(min_length=1, max_length=64)
    route: str = Field(pattern=ROUTE_PATTERN)
    flight_date: dt.date
    capacity: int = Field(gt=0)
    price_cents: int = Field(ge=0)


class FlightOut(BaseModel):
    flight_id: str
    route: str
    flight_date: dt.date
    seats_available: int
    price_cents: int


class ReservationIn(BaseModel):
    flight_id: str = Field(min_length=1, max_length=64)
    passenger_name: str = Field(min_length=1, max_length=200)
    fare_class: Literal["ECONOMY", "BUSINESS"]


class ReservationOut(BaseModel):
    reservation_id: str
    flight_id: str
    status: str
    passenger_name: str


class OccupancyOut(BaseModel):
    route: str
    month: str
    occupancy: float
    seats_sold: int
    seats_capacity: int
